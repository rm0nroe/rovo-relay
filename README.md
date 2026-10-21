# CLI-Anything Rovo

An experimental local command that lets a coding agent ask Rovo through an existing signed-in Chrome session. Browser interaction and waiting happen inside Playwright; the agent receives a bounded JSON result. Built using the CLI-Anything workflow, Python/Click and the upstream ReplSkin. This is not an official Atlassian or HKUDS client.

The repository is private. Changing visibility requires an explicit owner instruction.

## What works

- New-chat text questions with optional PNG images and GitHub chat source selection.
- Follow-up questions using an observed conversation ID.
- Loaded conversation listing and bounded text exports.
- Exact site/account checks, draft preservation and conservative uncertain-delivery handling.
- Installable command, interactive REPL and an on-demand Copilot skill.

Live browser tests passed on one development Mac. Actual GitHub file retrieval failed on that test site. Headless execution, other machines and invocation from VS Code Copilot remain unverified. See [validation](docs/VALIDATION.md).

## Install

Requires Python 3.11 or newer, Chrome and permission to attach through Chrome's remote-debugging connection. Tested on macOS with Python 3.14. The CLI does not configure debugging, install extensions, copy credentials, sign in or start a separate browser automatically. Chrome may require interactive approval for each connection. Use only a machine and browser where this access is permitted.

From the cloned repository, on macOS or Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
cli-anything-rovo --json doctor
```

The command can then run from any directory while that environment is active. Windows and Linux browser behavior have not been accepted. No Playwright browser download is required for the existing-Chrome mode.

## First use

Open exactly one Jira tab for the intended site, sign in normally and open its Rovo panel. Close any unsent draft before running a command. Substitute your own site and account below; examples contain no configured account.

```sh
cli-anything-rovo --json \
  --site https://example.atlassian.net/jira \
  --session pilot --account user@example.com status
```

The browser permission grants access to the Chrome session. The adapter limits its operations to the matching Jira site and expected account, but that is not a browser-enforced restriction to one tab.

Write a question to a private local UTF-8 file, then:

```sh
cli-anything-rovo --json \
  --site https://example.atlassian.net/jira \
  --session pilot --account user@example.com \
  ask --prompt-file question.txt
```

Add `--image diagram.png`, `--github-source on` or `--chat CONVERSATION_UUID` to `ask`. PNG attachments are limited to four files of 5 MiB each by local policy. Only one image per request has live acceptance. GitHub selection changes the chat filter, not connector installation, repository permissions or indexing.

With the same global site/session/account flags, use:

```text
chat list
chat export --chat CONVERSATION_UUID
ask --chat CONVERSATION_UUID --prompt-file follow-up.txt
```

Copy an ID from `chat list`; do not guess it. Listing and export cover currently loaded history only. Export contains user/assistant text, not original image bytes, intermediate progress or hidden model context. New-chat ID capture and structured citation extraction are not implemented.

## Output and recovery

One-shot commands produce schema-versioned JSON. `--help` produces text. `ask --timeout` defaults to a 180-second response budget, configurable from 1 to 600 seconds; preparation and browser operations have their own waits. Answers are capped at 12,000 characters and exports at 24,000, with truncation indicators. `context_percent` remains null because no verified meter is exposed.

Global `--dry-run` validates inputs without contacting the browser or writing request state. With no command in an interactive terminal, the CLI opens the standard CLI-Anything REPL. Include site/session/account for each browser command; REPL history is not saved.

| Exit | Meaning |
|---|---|
| 0 | Operation completed; this does not prove grounded retrieval |
| 1 | Argument, browser or preparation error; inspect submission state |
| 2 | Expected authenticated UI not found |
| 3 | Timeout or interruption; delivery may be uncertain |
| 4 | Prior uncertain request blocks another ask |

A site-level lock serializes this harness's commands. It cannot prevent another agent or a person from changing the tab. Request metadata is stored beneath the current user's home in `.cli-anything-rovo/SITE/SESSION/`. An uncertain attempt blocks another ask in that session. Do not delete records, remove locks or change session names to bypass that guard. Inspect the exact remote conversation before manual recovery. Automated reconciliation is not implemented.

## Copilot

The repository includes `.github/skills/rovo/SKILL.md`, with the same instructions bundled in the package. To use it in another project, review and copy the skill without overwriting an existing one. Put the installed CLI on the terminal PATH used by that project. Supply the destination site, expected account and session when invoking the skill. Actual VS Code invocation still needs acceptance on the target machine.

## Privacy and usage

Runtime results can contain account identity, site, chat IDs and proprietary answers; `doctor` returns a locally resolved skill path. These values are supplied or resolved on the user's machine, not embedded in the repository. Keep outputs, prompt files, images and browser data private and outside version control. No bridge-operated telemetry is added. Uninstalling the package does not delete local records or provider-held chats.

Rovo requests consume Rovo's metered allowance. This is not free or unlimited inference, and Copilot still processes the returned result. Token savings have not been measured. Check available allowance before live tests; the CLI does not enforce a credit budget or enable extra usage. Natural-language research instructions do not enforce read-only permissions in the connected provider.

## Local tests

```sh
python -m pip install pytest==9.1.1
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/rovo/tests -v
```

These checks do not contact Rovo. See [architecture](docs/ARCHITECTURE.md), [privacy review](docs/PRIVACY_REVIEW.md), [validation](docs/VALIDATION.md) and [upstream attribution](NOTICE).
