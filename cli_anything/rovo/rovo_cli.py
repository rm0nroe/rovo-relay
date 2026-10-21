"""Rovo Relay: first existing-browser slice."""
import importlib.metadata
import json
import os
import platform
import shlex
import sys
from pathlib import Path

import click

from cli_anything.rovo import __version__
from cli_anything.rovo.core.state import load_images, validate_target
from cli_anything.rovo.core.handoff import begin_handoff, finish_handoff
from cli_anything.rovo.utils.rovo_backend import operate


@click.group(invoke_without_command=True)
@click.option("--json", "json_mode", is_flag=True, help="Versioned JSON (also the one-shot default).")
@click.option("--site")
@click.option("--session")
@click.option("--account", help="Expected Atlassian account email, checked before sending.")
@click.option("--dry-run", is_flag=True, help="Validate only; do not touch browser or request state.")
@click.pass_context
def cli(ctx, json_mode, site, session, account, dry_run):
    """Experimental existing-Chrome bridge. See packaged skill for implemented scope."""
    ctx.obj = dict(site=site, session=session, account=account, dry_run=dry_run)
    if ctx.invoked_subcommand is None:
        if json_mode or not sys.stdin.isatty():
            raise click.UsageError("Choose doctor, status, chat or ask for noninteractive use.")
        repl()


@cli.command()
def doctor():
    """Report runtime and packaged skill; never claims authentication."""
    return {"schema_version": 1, "execution_status": "completed", "version": __version__,
            "python": platform.python_version(), "platform": platform.system(),
            "playwright": importlib.metadata.version("playwright"),
            "skill_path": str(Path(__file__).parent / "skills" / "SKILL.md"),
            "authenticated": "not_checked", "implemented": ["doctor", "status", "chat list", "chat export", "mcp begin", "mcp finish", "ask (new or existing chat, PNG images, GitHub source filter)"],
            "mcp_handoff": "agent_tools_with_local_guard",
            "browser_requirement": "Direct mode needs approved Chrome debugging; skill fallback needs an already-permitted Playwright MCP session"}, 0


def target(ctx):
    config = ctx.obj
    origin = validate_target(config["site"], config["session"], config["account"])
    return origin, config["session"], config["account"]


@cli.command()
@click.pass_context
def status(ctx):
    """Check exact account and Rovo UI; report prior attempt without reconciling it."""
    args = target(ctx)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True, "site": args[0]}, 0
    return operate(*args)


@cli.command()
@click.option("--prompt-file", required=True, type=click.File("r", encoding="utf-8"), help="Text file, or - for stdin.")
@click.option("--timeout", type=click.IntRange(1, 600), default=180, show_default=True)
@click.option("--image", multiple=True, type=click.Path(exists=True, dir_okay=False), help="PNG to upload, repeatable; at most four, 5 MiB each (local policy).")
@click.option("--github-source", type=click.Choice(["on", "off"]), help="Set the chat's GitHub source filter, not connector permissions.")
@click.option("--chat", type=click.UUID, help="Continue an observed conversation UUID; omit for a new chat.")
@click.pass_context
def ask(ctx, prompt_file, timeout, image, github_source, chat):
    """Send a prompt and optional PNG images in a new chat. Never retries uncertain delivery."""
    args = target(ctx)
    prompt = prompt_file.read(120001).strip()
    if not prompt or len(prompt) > 120000:
        raise click.UsageError("Prompt must contain 1 to 120000 characters (local policy).")
    images = load_images(image)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True,
                "site": args[0], "submission_state": "not_attempted", "prompt_characters": len(prompt),
                "image_count": len(images), "image_bytes": sum(len(item["buffer"]) for item in images),
                "github_source_requested": github_source, "chat_id": str(chat) if chat else None}, 0
    return operate(*args, prompt=prompt, timeout=timeout, images=images, github_source=github_source,
                   chat_id=str(chat) if chat else None)


@cli.group()
def chat():
    """List and export visible conversations, with explicit coverage limits."""


@chat.command("list")
@click.pass_context
def chat_list(ctx):
    args = target(ctx)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True, "action": "chat_list"}, 0
    return operate(*args, action="chat_list")


@chat.command("export")
@click.option("--chat", "chat_id", required=True, type=click.UUID)
@click.pass_context
def chat_export(ctx, chat_id):
    args = target(ctx)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True, "chat_id": str(chat_id)}, 0
    return operate(*args, action="chat_export", chat_id=str(chat_id))


@cli.group()
def mcp():
    """Guard an agent-mediated MCP handoff; these commands never connect to MCP or Chrome."""


@mcp.command("begin")
@click.option("--prompt-file", required=True, type=click.File("r", encoding="utf-8"))
@click.option("--before-count", required=True, type=click.IntRange(min=0))
@click.pass_context
def mcp_begin(ctx, prompt_file, before_count):
    """Reserve the site immediately before the agent's one MCP Submit click."""
    args = target(ctx)
    prompt = prompt_file.read(120001).strip()
    if not 1 <= len(prompt) <= 120000:
        raise click.UsageError("Prompt must contain 1 to 120000 characters.")
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "dry_run": True, "submission_state": "not_attempted"}, 0
    try:
        result = begin_handoff(Path.home(), *args, prompt, before_count)
        return result | {"schema_version": 1, "execution_status": "reserved", "retry_safe": False}, 0
    except (ValueError, OSError):
        return {"schema_version": 1, "execution_status": "blocked", "submission_state": "attempted_unknown",
                "retry_safe": False, "message": "MCP reservation failed or prior delivery is unresolved. Do not submit; inspect local state."}, 4


@mcp.command("finish")
@click.option("--evidence-file", required=True, type=click.File("r", encoding="utf-8"))
@click.pass_context
def mcp_finish(ctx, evidence_file):
    """Validate agent-observed completion; never resubmit or clear uncertain delivery."""
    args = target(ctx)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "dry_run": True, "state_changed": False}, 0
    try:
        raw = evidence_file.read(2000001)
        if len(raw) > 2000000:
            raise ValueError("Evidence is too large")
        return finish_handoff(Path.home(), *args, json.loads(raw)), 0
    except (ValueError, OSError):
        return {"schema_version": 1, "execution_status": "blocked", "submission_state": "attempted_unknown",
                "retry_safe": False, "message": "Completion evidence is invalid, mismatched or incomplete. Leave the request blocked; do not resubmit."}, 4


def run(args):
    try:
        result = cli.main(args=args, standalone_mode=False)
        if result is None or isinstance(result, int):
            return 0
        payload, code = result
    except (click.ClickException, ValueError, OSError) as error:
        payload, code = {"schema_version": 1, "execution_status": "error", "message": str(error),
                         "submission_state": "not_attempted", "retry_safe": True}, 1
    except KeyboardInterrupt:
        payload, code = {"schema_version": 1, "execution_status": "interrupted",
                         "submission_state": "attempted_unknown", "retry_safe": False}, 3
    print(json.dumps(payload, ensure_ascii=False))
    return code


def repl():
    from cli_anything.rovo.utils.repl_skin import ReplSkin
    skin = ReplSkin("rovo-relay", version=__version__, history_file=os.devnull)
    skin.skill_install_cmd = "Copy the packaged skills directory into .github/skills/ask-rovo (including MCP_FALLBACK.md)"
    skin.print_banner()
    prompt = skin.create_prompt_session()
    while True:
        try:
            line = skin.get_input(prompt)
            if line in ("quit", "exit"):
                break
            if line == "help":
                skin.help({"doctor": "Runtime and skill path", "status": "Check existing Rovo tab",
                           "ask": "New-chat text prompt; use --prompt-file", "quit": "Exit"})
            elif line:
                args = shlex.split(line)
                if args:
                    run(args)
        except (EOFError, KeyboardInterrupt):
            break
        except ValueError as error:
            skin.error(str(error))
    skin.print_goodbye()


def main():
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
