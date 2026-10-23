# Rovo Relay CLI

An experimental local command that lets a coding agent ask Rovo through an existing signed-in Chrome session. Direct browser interaction and waiting happen inside Playwright; the agent receives a bounded JSON result. The `/ask-rovo` skill can automatically use Copilot's existing permitted Playwright MCP session when direct Chrome attachment is blocked before submission. Built using the CLI-Anything workflow, Python/Click and the upstream ReplSkin. This is not an official Atlassian or HKUDS client.

This is an experimental, unofficial client. See the validation notes before live use.

## What works

- New-chat text questions with optional PNG images and GitHub chat source selection.
- Follow-up questions using an observed conversation ID.
- Loaded conversation listing and bounded text exports.
- Exact site/account checks, draft preservation and conservative uncertain-delivery handling.
- Installable command, persistent foreground JSON-lines session, interactive REPL and an on-demand Copilot skill.
- Agent-mediated MCP fallback with durable local delivery guards (offline-tested; live acceptance pending).

Live browser tests passed on one development Mac. Actual GitHub file retrieval failed on that test site. Headless execution, other machines and invocation from VS Code Copilot remain unverified. See [validation](docs/VALIDATION.md).

## Install

Requires Python 3.11 or newer, Chrome and permission to attach through Chrome's remote-debugging connection. Tested on macOS with Python 3.14. The CLI does not configure debugging, install extensions, copy credentials, sign in or start a separate browser automatically. Chrome may require interactive approval for each connection. Use only a machine and browser where this access is permitted.

From the cloned repository, on macOS or Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
rovo-relay-cli --json doctor
```

The command can then run from any directory while that environment is active. Version 0.1.0a5 names the command `rovo-relay-cli`; `rovo-relay` remains a compatibility alias. The Python distribution remains `rovo-relay`, so upgrading the existing installation replaces the same package. Version 0.1.0a3 adds persistent sessions; 0.1.0a4 adds explicit loopback port selection when Chrome lacks a discovery file. Windows and Linux browser behavior have not been accepted. No Playwright browser download is required for the existing-Chrome mode.


### Chrome connection setup

Opening Jira and signing in does not enable browser automation. This connection mode requires Chrome 144+ with remote debugging explicitly enabled in `chrome://inspect/#remote-debugging`. Keep Chrome open, run the account-bound `status` command, and approve Chrome's connection prompt yourself. The permission covers the Chrome session, not only Rovo. Follow your organization's policy; if the setting is unavailable or managed, report it instead of bypassing it. See [Chrome's documented setup](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session). No MCP installation is needed by Rovo Relay CLI.

Run the CLI in the same OS and user environment as normal Chrome. The adapter uses Playwright's `chrome` channel discovery for the default Chrome data location; WSL, containers, remote terminals, other Chrome channels and custom data locations are not automatically matched to the host browser.

`DevToolsActivePort file not found` means discovery could not read the connection file. It does not prove an authentication or GitHub failure, or by itself identify whether debugging is disabled, the browser is unsupported, or the runtime is looking in a different environment. The CLI now returns `error_code: chrome_debugging_unavailable` and `next_steps` without exposing the local profile path. Do not create that file manually or launch a replacement browser with debugging flags. Enable the supported setting if permitted, then retry only `status`. If it still fails, provide the browser version/channel, runtime environment and setting state using the setup prompt's blocker report.

Before each new attachment, the CLI flushes a connection notice to stderr; reused connections do not repeat it. Other attachment failures return `chrome_connection_failed`, sanitized guidance and measured `attachment_elapsed_ms`. Failure JSON also reports `attachment_phase` (`runtime_startup` or `browser_attachment`) and `attachment_timeout_ms` (the configured 20,000 ms CDP-call budget, not a startup or outer-tool deadline). Elapsed time includes runtime startup. These fields do not identify whether Chrome requested or received approval. Pending approval is a possible cause, not a confirmed diagnosis. This error does not automatically qualify for MCP fallback. A lost established connection returns `chrome_connection_lost`; sessions never reconnect automatically.

Debugging can be enabled and listening even when `DevToolsActivePort` is absent. In that case, pass global `--chrome-port PORT` before the command, using the port shown by Chrome's debugging UI or independently verified as owned by the intended normal Chrome process. This connects directly to `ws://127.0.0.1:PORT/devtools/browser` without file or HTTP discovery; Chrome's approval still applies. Only ports 1 through 65535 are accepted. Do not guess ports, use another profile, create the discovery file or restart Chrome with debugging flags. With no port supplied, normal channel discovery is unchanged. An explicit-port failure stops without falling back to another endpoint.

## First use

Sign in normally in the approved Chrome profile. The CLI opens its own tab at the requested site's `/jira/for-you`, verifies the expected account, opens Ask Rovo if needed, and waits up to 10 seconds for the panel and composer after navigation (also bounded to 10 seconds). Existing Jira/Rovo tabs stay untouched, even with multiple panels or drafts. One retained connection reuses its own tab for each site/session/account; a closed tab is replaced only after the site-wide unresolved-delivery guard passes. A tab that navigates outside Jira is retained and rejected. The CLI never reloads a tab or retries a submission. Requests still require an idle composer; drafts, attachments and active responses block sends. Substitute your own site and account below; examples contain no configured account.

```sh
rovo-relay-cli --json \
  --site https://example.atlassian.net/jira \
  --session pilot --account user@example.com status
```

The floating mini-modal supports account-bound read-only `status`: `readiness: authenticated_ui_read_only` and `active_generation: null`. A completed status check confirms the account, panel and visible composer; it does not establish safe sending or a completed response. Ask, list and export remain blocked with `error_code: rovo_layout_unverified` (exit 1). Its response cards and message groups are observed, but generation, attachment-state handling and reliable completion remain unverified. `Message sent.` is not a completion signal; neither an empty composer nor disabled New chat establishes safety. Do not switch transports to bypass these limits. Legacy operations require one visible enabled idle composer. A new conversation uses New chat when enabled; a disabled button is skipped only on the verified empty welcome screen, with no message groups or response cards and a visible disabled Submit button. Other disabled-button states remain blocked. This empty-sidebar path is offline-tested; live sending from that state remains unverified.

The browser permission grants access to the Chrome session. The adapter limits its operations to the matching Jira site and expected account, but that is not a browser-enforced restriction to one tab.

## Persistent agent session

Keep one foreground process alive for the whole interaction:

```sh
rovo-relay-cli --site https://example.atlassian.net \
  --session pilot --account user@example.com session
```

If file discovery fails while debugging is enabled, add `--chrome-port PORT` before `session` using the verified port described above. The process attaches lazily after checking the site's delivery guard, runs one startup status and flushes its schema-1 JSON result with `exit_code`. Wait for that result before writing commands. A nonzero startup code ends the process. The initial approval is still required; keeping the process alive avoids a new attachment for every command. The selected Chrome port is fixed for that connection, including in the REPL.

Send one JSON argv array per line on stdin. For example, `["status"]` performs another read-only check. After send readiness, available credits and user authorization are established, `["ask", "--prompt-file", "/path/to/question.txt"]` uses the same connection. Existing `chat list`, `chat export` and ask options use their usual argv form. Keep the process's stdin open between commands; closing it ends the session. Do not start a separate status/ask process for each step.

At shutdown, the CLI closes only its own verified empty, idle legacy-panel tab after status. It retains tabs with conversation content, drafts, uncertain submissions, failed preparation or unverified layouts and reports retention on stderr; existing user tabs are never closed. Separate one-shot invocations each create a new tab, so use `session` for reuse. Chrome focus may change when a tab opens. Account expiry, managed restrictions and unsupported layouts still require resolution; bounded waiting does not repair a broken frontend. Results include `tab_selection: connection_owned`, `readiness_phase` and `readiness_timeout_ms` to distinguish preparation from attachment failures.

Each input line receives one flushed JSON result with `exit_code`; stdout contains no banner or echo. Site, account, request-session and dry-run policy are fixed at startup. Only status, ask and chat commands are accepted. Malformed input, help, global overrides, nested sessions, MCP commands and `--prompt-file -` (including `=-`) are refused. Preparation/argument errors leave the connection open. Authentication failure, blocked delivery, interruption, lost connection or an unsuccessful possibly-submitted operation ends the process. A completed ask may continue even with `retry_safe: false`; that value forbids resending the completed turn.

Every operation rechecks delivery state, eligible tabs, unique panel, account and applicable composer guards. Locks are released between commands; no DOM or readiness result is cached. EOF, Ctrl-C, SIGTERM and errors detach the client without closing external Chrome tabs. Cleanup errors go to stderr without replacing the command result. Global `--dry-run session` validates startup arguments, emits one result and exits without attaching or reading commands. One-shot commands remain available and attach/detach independently.

For a one-shot operation, write a question to a private local UTF-8 file, then:

```sh
rovo-relay-cli --json \
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

Global `--dry-run` validates inputs without contacting the browser or writing request state. With no command in an interactive terminal, the CLI opens the standard CLI-Anything REPL, which also retains one lazy connection until exit. Include site/session/account for each browser command; REPL history is not saved. Connection failure ends the REPL without a silent reconnect.

| Exit | Meaning |
|---|---|
| 0 | Operation completed; this does not prove grounded retrieval |
| 1 | Argument, browser or preparation error; inspect submission state |
| 2 | Expected authenticated UI not found |
| 3 | Timeout or interruption; delivery may be uncertain |
| 4 | Prior uncertain request blocks another ask |

A site-level lock serializes this harness's commands. It cannot prevent another agent or a person from changing the tab. Both command names intentionally share the original state directory so renaming cannot bypass unresolved delivery. Request metadata is stored beneath the current user's home in `.cli-anything-rovo/SITE/SESSION/`; MCP reservations use `.cli-anything-rovo/SITE/.mcp/`. An uncertain attempt blocks another send across all sessions and both transports on that site. Do not delete records, remove locks or change session names to bypass that guard. Inspect the exact remote conversation before manual recovery. Automated reconciliation is not implemented.

## Copilot

Use the [copy-and-paste Copilot setup prompt](docs/COPILOT_SETUP_PROMPT.md) to install and test on another machine.

Invoke the skill as `/ask-rovo`. The repository includes `.github/skills/ask-rovo/SKILL.md`, with its `MCP_FALLBACK.md` reference, both also bundled in the package. To use it in another project, review and copy the entire `ask-rovo` skill folder without overwriting local customizations. Put the installed CLI on the terminal PATH used by that project. Supply the destination site, expected account and session when invoking the skill. Actual VS Code invocation still needs acceptance on the target machine.

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
