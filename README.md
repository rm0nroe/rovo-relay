# Rovo Relay

An experimental local command that lets a coding agent ask Rovo through an existing signed-in Chrome session. Direct browser interaction and waiting happen inside Playwright; the agent receives a bounded JSON result. The `/ask-rovo` skill can automatically use Copilot's existing permitted Playwright MCP session when direct Chrome attachment is blocked before submission. Built using the CLI-Anything workflow, Python/Click and the upstream ReplSkin. This is not an official Atlassian or HKUDS client.

This is an experimental, unofficial client. See the validation notes before live use.

## What works

- New-chat text questions with optional PNG images and GitHub chat source selection.
- Follow-up questions using an observed conversation ID.
- Loaded conversation listing and bounded text exports.
- Exact site/account checks, draft preservation and conservative uncertain-delivery handling.
- Installable command, interactive REPL and an on-demand Copilot skill.
- Agent-mediated MCP fallback with durable local delivery guards (offline-tested; live acceptance pending).

Live browser tests passed on macOS. Actual GitHub file retrieval failed on that test site. Headless execution, other operating systems and invocation from VS Code Copilot remain unverified. See [validation](docs/VALIDATION.md).

## Install

Requires Python 3.11 or newer, Chrome and permission to attach through Chrome's remote-debugging connection. Tested on macOS with Python 3.14. The CLI does not configure debugging, install extensions, copy credentials, sign in or start a separate browser automatically. Chrome may require interactive approval for each connection. Use only a machine and browser where this access is permitted.

From the cloned repository, on macOS or Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
rovo-relay --json doctor
```

The command can then run from any directory while that environment is active. Windows and Linux browser behavior have not been accepted. No Playwright browser download is required for the existing-Chrome mode.


### Chrome connection setup

Opening Jira and signing in does not enable browser automation. This connection mode requires Chrome 144+ with remote debugging explicitly enabled in `chrome://inspect/#remote-debugging`. Keep Chrome open, run the account-bound `status` command, and approve Chrome's connection prompt yourself. The permission covers the Chrome session, not only Rovo. Follow your organization's policy; if the setting is unavailable or managed, report it instead of bypassing it. See [Chrome's documented setup](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session). No MCP installation is needed by Rovo Relay.

Run the CLI in the same OS and user environment as normal Chrome. The adapter uses Playwright's `chrome` channel discovery for the default Chrome data location; WSL, containers, remote terminals, other Chrome channels and custom data locations are not automatically matched to the host browser.

`DevToolsActivePort file not found` means discovery could not read the connection file. It does not prove an authentication or GitHub failure, or by itself identify whether debugging is disabled, the browser is unsupported, or the runtime is looking in a different environment. The CLI now returns `error_code: chrome_debugging_unavailable` and `next_steps` without exposing the local profile path. Do not create that file manually or launch a replacement browser with debugging flags. Enable the supported setting if permitted, then retry only `status`. If it still fails, provide the browser version/channel, runtime environment and setting state using the setup prompt's blocker report.

## First use

Open exactly one Jira tab for the intended site, sign in normally and open its Rovo panel. Close any unsent draft before running a command. Substitute your own site and account below; examples contain no configured account.

```sh
rovo-relay --json \
  --site https://example.atlassian.net/jira \
  --session pilot --account user@example.com status
```

The browser permission grants access to the Chrome session. The adapter limits its operations to the matching Jira site and expected account, but that is not a browser-enforced restriction to one tab.

Write a question to a private local UTF-8 file, then:

```sh
rovo-relay --json \
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

A site-level lock serializes this harness's commands. It cannot prevent another agent or a person from changing the tab. Request metadata is stored beneath the current user's home in `.cli-anything-rovo/SITE/SESSION/`; MCP reservations use `.cli-anything-rovo/SITE/.mcp/`. An uncertain attempt blocks another send across all sessions and both transports on that site. Do not delete records, remove locks or change session names to bypass that guard. Inspect the exact remote conversation before manual recovery. Automated reconciliation is not implemented.

## Copilot

Use the [copy-and-paste Copilot setup prompt](docs/COPILOT_SETUP_PROMPT.md) to install and test through VS Code Copilot.

Invoke the skill as `/ask-rovo`. The repository includes `.github/skills/ask-rovo/SKILL.md`, with its `MCP_FALLBACK.md` reference, both also bundled in the package. To use it in another project, review and copy the entire `ask-rovo` skill folder without overwriting local customizations. Put the installed CLI on the terminal PATH used by that project. Supply the destination site, expected account and session when invoking the skill. Actual VS Code invocation still needs acceptance under Copilot.

### Automatic MCP fallback

Version 0.1.0a2 adds skill-level routing. The standalone `ask` command still uses direct Chrome; it does not inherit Copilot's MCP connection. If direct status fails before submission with `chrome_debugging_unavailable`, `not_attempted` and `retry_safe: true`, `/ask-rovo` checks the already-configured Playwright MCP and continues through it only if the intended signed-in Jira/Rovo tab is accessible with existing permissions. A user-confirmed policy block can use the same pre-submission check. No MCP installation, new browser, connector, cookie transfer or policy change is automatic.

The agent preserves drafts, verifies account/site, applies requested images/source/chat controls, then calls `mcp begin` immediately before one MCP submission. That local command saves a durable reservation before the click. The agent observes the response and supplies evidence to `mcp finish`, which validates the request, prompt hash, baseline count and terminal conditions before clearing the reservation. Both transports share the local site guard. A lost result, timeout, incomplete evidence or interruption stays blocked; no automatic retry or cross-transport resend occurs. These local commands do not control the browser themselves.

`mcp finish` reports `transport: playwright_mcp`, `completion_evidence: agent_observed` and `retrieval_assessment: unverified`. The CLI validates the supplied evidence but cannot independently attest the remote UI. Natural-language skill compliance, actual MCP permissions and host file access still need acceptance in Copilot. MCP mode may consume more context than the direct CLI. Read-only MCP inspection is not a passing direct CLI connection test.

## Privacy and usage

Runtime results can contain account identity, site, chat IDs and proprietary answers; `doctor` returns a locally resolved skill path. These values are supplied or resolved on the user's machine, not embedded in the repository. Keep outputs, prompt files, images and browser data private and outside version control. No bridge-operated telemetry is added. Uninstalling the package does not delete local records or provider-held chats.

Rovo requests consume Rovo's metered allowance. This is not free or unlimited inference, and Copilot still processes the returned result. Token savings have not been measured. Check available allowance before live tests; the CLI does not enforce a credit budget or enable extra usage. Natural-language research instructions do not enforce read-only permissions in the connected provider.

## Local tests

```sh
python -m pip install pytest==9.1.1
CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/rovo/tests -v
```

These checks do not contact Rovo. See [architecture](docs/ARCHITECTURE.md), [privacy review](docs/PRIVACY_REVIEW.md), [validation](docs/VALIDATION.md) and [upstream attribution](NOTICE).
