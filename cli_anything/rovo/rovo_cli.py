"""Rovo Relay CLI: first existing-browser slice."""
import importlib.metadata
import json
import os
import platform
import shlex
import signal
import socket
import sys
from contextlib import contextmanager
from pathlib import Path

import click

from cli_anything.rovo import __version__
from cli_anything.rovo.core.state import load_images, next_action, validate_target
from cli_anything.rovo.core.handoff import begin_handoff, finish_handoff
from cli_anything.rovo.utils.rovo_backend import BrowserConnection, operate


@click.group(invoke_without_command=True)
@click.option("--json", "json_mode", is_flag=True, help="Versioned JSON (also the one-shot default).")
@click.option("--site")
@click.option("--session")
@click.option("--account", help="Expected Atlassian account email, checked before sending.")
@click.option("--chrome-port", type=click.IntRange(1, 65535), help="Verified existing-Chrome loopback debugging port; preserves Chrome approval.")
@click.option("--approve-chrome-prompt", is_flag=True, help="Authorize guarded macOS approval for this CLI connection only; requires --chrome-port.")
@click.option("--dry-run", is_flag=True, help="Validate only; do not touch browser or request state.")
@click.pass_context
def cli(ctx, json_mode, site, session, account, chrome_port, approve_chrome_prompt, dry_run):
    """Experimental existing-Chrome bridge. See packaged skill for implemented scope."""
    connection = (ctx.obj or {}).get("connection")
    if connection is not None and chrome_port is not None and chrome_port != connection.chrome_port:
        raise click.UsageError("The active connection's Chrome port cannot change; exit the session first.")
    if connection is not None and approve_chrome_prompt and not connection.approve_chrome_prompt:
        raise click.UsageError("Chrome approval policy cannot change inside an active session.")
    ctx.obj = dict(approve_chrome_prompt=approve_chrome_prompt, site=site, session=session, account=account, chrome_port=chrome_port, dry_run=dry_run,
                   connection=(ctx.obj or {}).get("connection"))
    if ctx.invoked_subcommand is None:
        if ctx.obj["connection"] is not None or json_mode or not sys.stdin.isatty():
            raise click.UsageError("Choose doctor, session, status, chat or ask for noninteractive use.")
        return repl(chrome_port, approve_chrome_prompt)


def capabilities():
    return {"version": __version__,
            "implemented": ["doctor", "session", "status", "chat list", "chat export", "mcp begin", "mcp finish", "ask (new or existing chat, PNG images, GitHub source filter)", "automatic conversation continuity", "agent next action", "guarded Chrome prompt approval", "reconcile", "broker"],
            "mcp_handoff": "agent_tools_with_local_guard"}


def acted(result):
    """Direct results carry the agent's next action; MCP handoff keeps its own documented flow."""
    payload, code = result
    return payload | {"next": next_action(payload, code)}, code


@cli.command()
def doctor():
    """Report runtime and packaged skill; never claims authentication."""
    return {"schema_version": 1, "execution_status": "completed", **capabilities(),
            "python": platform.python_version(), "platform": platform.system(),
            "playwright": importlib.metadata.version("playwright"),
            "skill_path": str(Path(__file__).parent / "skills" / "SKILL.md"),
            "authenticated": "not_checked",
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
    return acted(operate(*args, connection=ctx.obj.get("connection"), chrome_port=ctx.obj.get("chrome_port"), approve_chrome_prompt=ctx.obj.get("approve_chrome_prompt", False)))


@cli.command()
@click.option("--prompt-file", required=True, type=click.File("r", encoding="utf-8"), help="Text file, or - for stdin.")
@click.option("--timeout", type=click.IntRange(1, 600), default=180, show_default=True)
@click.option("--image", multiple=True, type=click.Path(exists=True, dir_okay=False), help="PNG to upload, repeatable; at most four, 5 MiB each (local policy).")
@click.option("--github-source", type=click.Choice(["on", "off"]), help="Set the chat's GitHub source filter, not connector permissions.")
@click.option("--chat", type=click.UUID, help="Explicitly select an observed conversation UUID.")
@click.option("--new", is_flag=True, help="Start a separate conversation and replace this session's binding.")
@click.pass_context
def ask(ctx, prompt_file, timeout, image, github_source, chat, new):
    """Continue this session's verified chat, or create its first chat. Never retries delivery."""
    args = target(ctx)
    prompt = prompt_file.read(120001).strip()
    if not prompt or len(prompt) > 120000:
        raise click.UsageError("Prompt must contain 1 to 120000 characters (local policy).")
    if new and chat:
        raise click.UsageError("Use either --new or --chat, not both.")
    images = load_images(image)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True,
                "site": args[0], "submission_state": "not_attempted", "prompt_characters": len(prompt),
                "image_count": len(images), "image_bytes": sum(len(item["buffer"]) for item in images),
                "conversation_mode": "new" if new else "explicit" if chat else "automatic",
                "github_source_requested": github_source, "chat_id": str(chat) if chat else None}, 0
    return acted(operate(*args, prompt=prompt, timeout=timeout, images=images, github_source=github_source,
                         chat_id=str(chat) if chat else None, new=new, connection=ctx.obj.get("connection"), chrome_port=ctx.obj.get("chrome_port"), approve_chrome_prompt=ctx.obj.get("approve_chrome_prompt", False)))


@cli.command()
@click.pass_context
def reconcile(ctx):
    """Lift this session's uncertain-delivery block only if Rovo's own history proves it; never sends."""
    args = target(ctx)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True, "action": "reconcile"}, 0
    return acted(operate(*args, action="reconcile", connection=ctx.obj.get("connection"), chrome_port=ctx.obj.get("chrome_port"), approve_chrome_prompt=ctx.obj.get("approve_chrome_prompt", False)))


@cli.group()
def chat():
    """List and export visible conversations, with explicit coverage limits."""


@chat.command("list")
@click.pass_context
def chat_list(ctx):
    args = target(ctx)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True, "action": "chat_list"}, 0
    return acted(operate(*args, action="chat_list", connection=ctx.obj.get("connection"), chrome_port=ctx.obj.get("chrome_port"), approve_chrome_prompt=ctx.obj.get("approve_chrome_prompt", False)))


@chat.command("export")
@click.option("--chat", "chat_id", required=True, type=click.UUID)
@click.pass_context
def chat_export(ctx, chat_id):
    args = target(ctx)
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True, "chat_id": str(chat_id)}, 0
    return acted(operate(*args, action="chat_export", chat_id=str(chat_id), connection=ctx.obj.get("connection"), chrome_port=ctx.obj.get("chrome_port"), approve_chrome_prompt=ctx.obj.get("approve_chrome_prompt", False)))


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


def preparation_error(error):
    return acted(({"schema_version": 1, "execution_status": "error", "message": str(error),
                   "submission_state": "not_attempted", "retry_safe": True}, 1))


def invoke(args, command=cli, obj=None):
    try:
        return command.main(args=args, obj=obj, standalone_mode=False)
    except (click.ClickException, ValueError, OSError) as error:
        return preparation_error(error)
    except (KeyboardInterrupt, click.Abort):
        return {"schema_version": 1, "execution_status": "interrupted",
                "submission_state": "attempted_unknown", "retry_safe": False}, 3


def emit(result, stream=False):
    payload, code = result
    print(json.dumps(payload | ({"exit_code": code} if stream else {}), ensure_ascii=False), flush=True)
    return code


# One-shot commands a running broker serves on its connection; everything else runs here.
FORWARDED = ("status", "ask", "chat", "reconcile")


def broker_path():
    return Path.home() / ".cli-anything-rovo" / "broker.sock"


def subcommand(args):
    """The command name: the first argument that is neither a global option nor its value."""
    valued = {opt for param in cli.params if not getattr(param, "is_flag", False) for opt in param.opts}
    skip = False
    for arg in args:
        if skip or arg in valued:
            skip = not skip and arg in valued
            continue
        if not arg.startswith("-"):
            return arg
    return None


def forward(args):
    """The live broker's result for args, or None when no broker is listening (run directly)."""
    if subcommand(args) not in FORWARDED or {"--dry-run", "--help", "-h"} & set(args) or any(
            arg == "--prompt-file=-" or (arg == "--prompt-file" and args[i + 1:i + 2] == ["-"]) for i, arg in enumerate(args)):
        return None
    client = socket.socket(socket.AF_UNIX)
    try:
        client.connect(str(broker_path()))
    except OSError:
        client.close()
        return None
    with client:
        try:
            client.sendall(json.dumps({"argv": args, "cwd": os.getcwd()}).encode() + b"\n")
            reply = json.loads(client.makefile(encoding="utf-8").readline())
            return reply["payload"], reply["code"]
        except (OSError, ValueError, KeyError, TypeError):
            # The broker may have acted; never fall back to sending directly.
            return acted(({"schema_version": 1, "execution_status": "error", "submission_state": "attempted_unknown",
                           "retry_safe": False, "message": "Broker ended before replying; run status before anything else, never resubmit."}, 3))


def run(args):
    result = forward(args) or invoke(args)
    return emit(result) if isinstance(result, tuple) else result or 0


@cli.command()
@click.option("--idle-minutes", type=click.FloatRange(0, 1440, min_open=True), default=30.0, show_default=True)
@click.pass_context
def broker(ctx, idle_minutes):
    """Hold one approved Chrome connection for later one-shot commands by this user; exits when idle."""
    if ctx.obj.get("connection") is not None:
        raise click.UsageError("broker cannot run inside a session.")
    if ctx.obj["dry_run"]:
        return {"schema_version": 1, "execution_status": "completed", "dry_run": True}, 0
    path = broker_path()
    probe = socket.socket(socket.AF_UNIX)
    try:
        probe.connect(str(path))
        return preparation_error(ValueError("A broker is already running for this user."))
    except OSError:
        path.unlink(missing_ok=True)  # Stale socket from a broker that did not exit cleanly.
    finally:
        probe.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    server = socket.socket(socket.AF_UNIX)
    umask = os.umask(0o177)  # Owner-only socket from the moment it exists.
    try:
        server.bind(str(path))
    finally:
        os.umask(umask)
    server.listen(8)
    server.settimeout(idle_minutes * 60)
    reason = "interrupted"
    try:
        with foreground_connection(ctx.obj["chrome_port"], ctx.obj["approve_chrome_prompt"]) as connection:
            try:
                connection.get()
            except ValueError as error:
                return {"schema_version": 1, "execution_status": "error", "message": str(error), **connection.diagnostics,
                        "submission_state": "not_attempted", "retry_safe": True}, 1
            emit(({"schema_version": 1, "execution_status": "ready", "idle_minutes": idle_minutes, **capabilities()}, 0), stream=True)
            # ponytail: one command at a time; others queue on the socket. Concurrency needs per-site locking first.
            while not connection.failed:
                try:
                    client, _ = server.accept()
                except TimeoutError:
                    reason = "idle"
                    break
                with client:
                    line = client.makefile(encoding="utf-8").readline()
                    if not line:
                        continue  # A liveness probe, or a client that hung up before asking.
                    try:
                        request = json.loads(line)
                        os.chdir(request["cwd"])
                        result = invoke(list(request["argv"]), obj={"connection": connection})
                        if not isinstance(result, tuple):
                            raise ValueError("no result")
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        result = preparation_error(ValueError("Malformed broker request: " + type(error).__name__))
                    payload, code = result
                    emit(result, stream=True)
                    try:
                        client.sendall(json.dumps({"payload": payload, "code": code}, ensure_ascii=False).encode() + b"\n")
                    except OSError:
                        pass  # The client left; its result is in the log line above and in local state.
            else:
                reason = "connection_lost"
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        path.unlink(missing_ok=True)
    return {"schema_version": 1, "execution_status": "stopped", "reason": reason}, 0


@contextmanager
def foreground_connection(chrome_port=None, approve_chrome_prompt=False):
    def interrupt(signum, frame):
        raise KeyboardInterrupt

    previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        with BrowserConnection(chrome_port, approve_chrome_prompt) as connection:
            yield connection
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def terminal(result, connection):
    payload, code = result
    return (connection.failed or code in (2, 3, 4)
            or (code != 0 and payload.get("submission_state") != "not_attempted"))


def stream_command(line, config):
    try:
        args = json.loads(line)
        if (not isinstance(args, list) or not args or not all(isinstance(arg, str) for arg in args)
                or args[0] not in ("status", "ask", "chat") or "--help" in args or "-h" in args
                or (args[0] == "chat" and (len(args) < 2 or args[1] not in ("list", "export")))):
            raise ValueError("Expected a JSON argv array for status, ask or chat list/export, without help or global overrides.")
        if any(arg == "--prompt-file=-" or (arg == "--prompt-file" and args[i + 1:i + 2] == ["-"])
               for i, arg in enumerate(args)):
            raise ValueError("Session stdin belongs to the command stream; use a private prompt file.")
    except ValueError as error:
        return preparation_error(error)
    return invoke(args[1:], command=cli.commands[args[0]], obj=config)


@cli.command()
@click.pass_context
def session(ctx):
    """Retain one approved Chrome connection; read JSON argv arrays, emit JSON lines."""
    try:
        target(ctx)
    except ValueError as error:
        return emit(preparation_error(error), stream=True)
    if ctx.obj.get("connection") is not None:
        raise click.UsageError("A foreground session is already active.")
    if ctx.obj["dry_run"]:
        return emit(invoke([], command=status, obj=ctx.obj), stream=True)
    with foreground_connection(ctx.obj["chrome_port"], ctx.obj["approve_chrome_prompt"]) as connection:
        config = ctx.obj | {"connection": connection}
        result = invoke([], command=status, obj=config)
        emit((result[0] | capabilities(), result[1]), stream=True)
        if result[1]:
            return result[1]
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    return 0
                result = stream_command(line, config)
            except (KeyboardInterrupt, click.Abort):
                result = ({"schema_version": 1, "execution_status": "interrupted",
                           "submission_state": "not_attempted", "retry_safe": True}, 3)
            except Exception:
                result = ({"schema_version": 1, "execution_status": "error",
                           "message": "Command stream failed; inspect local state without resubmitting.",
                           "submission_state": "attempted_unknown", "retry_safe": False}, 1)
            emit(result, stream=True)
            if terminal(result, connection):
                return result[1]


def repl(chrome_port=None, approve_chrome_prompt=False):
    from cli_anything.rovo.utils.repl_skin import ReplSkin
    skin = ReplSkin("rovo-relay-cli", version=__version__, history_file=os.devnull)
    skin.skill_install_cmd = "Copy the packaged skills directory into .github/skills/ask-rovo (including MCP_FALLBACK.md)"
    skin.print_banner()
    prompt = skin.create_prompt_session()
    code = 0
    with foreground_connection(chrome_port, approve_chrome_prompt) as connection:
        while True:
            try:
                line = skin.get_input(prompt)
                if line in ("quit", "exit"):
                    break
                if line == "help":
                    skin.help({"doctor": "Runtime and skill path", "status": "Check existing Rovo tab",
                               "ask": "Continue session chat; --new starts another; use --prompt-file", "quit": "Exit"})
                elif line:
                    args = shlex.split(line)
                    if args:
                        result = invoke(args, obj={"connection": connection})
                        if isinstance(result, tuple):
                            code = emit(result)
                            if terminal(result, connection):
                                break
            except EOFError:
                break
            except KeyboardInterrupt:
                code = 3
                break
            except ValueError as error:
                skin.error(str(error))
    skin.print_goodbye()
    return code


def main():
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
