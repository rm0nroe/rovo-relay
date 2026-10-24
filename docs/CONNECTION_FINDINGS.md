# Connection findings

Local code and evidence reviewed at `7de0fbc` on 2026-10-23. External capability research below was checked on 2026-10-22; it is not target-organization acceptance or a fresh connector check.

## Decision

Do not add a daemon, change Chrome policy, or raise a timeout yet. The existing `session` command is the smallest available reuse mechanism: it owns one `BrowserConnection` until stdin reaches EOF or a terminal result occurs. That is local behavior, not evidence that Copilot retains a process or streams across skill invocations. [Local source](../cli_anything/rovo/rovo_cli.py)

Check official access before expanding the bridge: MCP v2 documents full-file retrieval, and A2A documents delegation to Rovo. Target-organization availability remains unverified. Local retained-process checks have passed; the remaining host gate is one approved foreground session in the actual Copilot host followed by a later, status-only command sent to that **same process**. Capture private evidence of one PID, open stdin/stdout handles, one attachment, and no intervening disconnect. A session label alone does not establish process continuity.

## Current local evidence

The installed CLI at `c9f380a` passed new-chat creation, switching from an existing conversation and automatic second-turn continuation after process restart and owned-tab closure. Each scenario used one additional authorized question. ID comparisons, exact read-only exports and saved signatures verified conversation identity; the process restart established conversation continuity, not reuse of the previous browser connection.

At `7de0fbc`, 249 installed offline tests passed. Read-only startup reproduced and then verified the fix for the narrow-window Ask Rovo timeout: Show more must remain open between account verification and the launcher click. A second status passed with the panel already open. No questions were sent for that fix. Detailed scope and historical results are in [Validation status](VALIDATION.md#current-development-baseline-2026-10-23).

## Official alternatives checked on 2026-10-22

| Need | Official capability | Remaining acceptance gate |
| --- | --- | --- |
| Retrieve code for the existing coding agent | MCP v2 `searchCode` finds matching lines; `getCodeFile` returns a complete file at a specified commit. The `search_code` group requires OAuth and `search:code:agent-interface`. | Discover the tools in the approved host; verify repository access and compare actual returned text with the same Git revision. |
| Keep tool discovery small | MCP v2 exposes primary tools plus `discover` and deferred execution through `executeRead`. | Measure the actual host workflow; do not assume token or cost savings. |
| Use a shell interface | TWG supplies Atlassian data tools; its current authentication guide specifies OAuth 2.1 for interactive use. | Verify installed command schemas and exact code-file coverage. Do not invent a TWG equivalent from an MCP tool name. |
| Delegate a question to Rovo | A2A supports compatible third-party agents asking Rovo questions and performing supported Jira/Confluence tasks. | Confirm host A2A support, organization enablement and OAuth access; this is not proof of GitHub retrieval or existing-chat continuity. |
| Run a separate coding agent | Rovo Dev CLI requires site activation and allocated Rovo Dev credits. | This alone does not establish a replacement for the existing coding agent's retrieval workflow. |

Sources: [MCP v2 tool catalog](https://support.atlassian.com/atlassian-ai-gateway/docs/supported-tools/), [current TWG authentication](https://support.atlassian.com/organization-administration/docs/how-does-teamwork-graph-cli-authentication-work/), [A2A setup](https://support.atlassian.com/atlassian-ai-gateway/docs/set-up-agent2agent-connections/), [Rovo Dev requirements](https://support.atlassian.com/rovo/docs/install-and-run-rovo-dev-cli-on-your-device/).

The older [TWG/Rovo MCP comparison](https://support.atlassian.com/rovo/docs/teamwork-graph-cli-and-rovo-mcp-decision-guide/) still describes TWG OAuth as planned. Prefer the dedicated authentication guide for that detail. The [current selection guide](https://support.atlassian.com/organization-administration/docs/choosing-between-twg-cli-and-atlassian-mcp/) permits either interface for desktop agents with terminal access. The bridge's browser delegation is therefore not established as uniquely necessary.

For GitHub, inspect the existing GitHub for Atlassian connection, repository scope, linked user identity, Code context state and initial-index status. The setup guide says initial indexing can take up to 48 hours. Its Bitbucket section now describes automatic rollout for qualifying workspaces, so the overview's blanket "off by default" language must not be generalized to every provider. This investigation must not enable indexing or change grants. [Code context setup](https://support.atlassian.com/organization-administration/docs/set-up-code-context-for-your-site/)

## Established facts

### Chrome connection approval

Chrome's documented automatic connection mode requires Chrome 144 or later, an explicit enablement at `chrome://inspect/#remote-debugging`, and an Allow or Disallow decision. The MCP server connects to the running default profile and can access that profile's open windows. [Chrome advanced usage](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/advanced-usage.md#automatically-connecting-to-a-running-chrome-instance)

Chrome DevTools MCP maintainers say a new auto-connect connection prompts again and that there is no simple persistent approval without letting local programs access Chrome data too easily. Their present recommendation is longer connection sessions; the persistence request was closed as not planned. [Issue #825](https://github.com/ChromeDevTools/chrome-devtools-mcp/issues/825)

This relay's `BrowserConnection.get()` makes one lazy CDP attachment per process and its `session` loop keeps that connection while stdin remains open. It closes the client when the loop ends. [Local source](../cli_anything/rovo/utils/rovo_backend.py) [Local source](../cli_anything/rovo/rovo_cli.py)

**Conclusion:** retaining the existing approved process is the supported near-term path to fewer prompts. Do not adopt dedicated-profile or browser-relaunch workarounds. The relay's existing `--chrome-port` option instead targets an independently verified, already-enabled normal-Chrome endpoint and preserves approval; it does not grant persistent permission. [Local source](../cli_anything/rovo/utils/rovo_backend.py)

### Timeout attribution

The relay records a 20-second timeout only on Playwright's `connect_over_cdp` call. Its elapsed field begins before Playwright runtime startup, so it is not an attachment-only measurement. [Local source](../cli_anything/rovo/utils/rovo_backend.py)

An MCP host, Copilot wrapper, process manager, or stream owner can impose a shorter deadline outside that call. The repository has no code or host receipt identifying any such outer limit. A reported seven-second failure therefore does **not** establish Chrome denial, CDP timeout, or a particular host timeout.

**Verification gate:** compare one existing failed trace and one successful trace from the same installed revision and environment. Record caller start/deadline/termination, the emitted connection notice, returned phase and elapsed fields, and CDP budget. Keep raw records outside Git. If the process dies before JSON output, classify it as a missing receipt.

Attachment failures and control-click failures are separate phases. `click_diagnostics` now reports a fixed control label, an allowlisted reason and `timed_out`, without raw Playwright logs. The narrow-window startup failure reported `Ask Rovo` / `detached` and is fixed. The older post-readiness pre-submit timeout and the Copilot-host shorter attachment failure remain unidentified; neither is explained by a successful restart or the overflow fix.

### Copilot process and stream lifetime

The local CLI can retain a connection only when its parent retains the foreground process and command streams. It has no IPC service, persisted owner, or cross-process connection store. [Local source](../cli_anything/rovo/rovo_cli.py) [Local source](../cli_anything/rovo/utils/rovo_backend.py)

It does persist a verified conversation binding in the private request record. A fresh process with the same site/session/account can attach anew and reopen that chat after matching its loaded history. This is distinct from retaining approval, a process or a connection across invocations.

Whether Copilot keeps those handles across separate invocations is unknown. No inspected source establishes Copilot's process, stdin/stdout, or child-process retention policy. Do not infer it from a matching `--session` value or an earlier successful status call.

If the status-only gate fails, document the host limitation before considering a separately scoped local owner. Any later owner must bind an approved site/account/port, serialize commands, use access-controlled local IPC, require explicit start/stop, have bounded idle cleanup, and retain the existing uncertain-delivery guard. That is a separate design and authorization gate.

### Rovo code context and GitHub retrieval

For the GitHub case, Code context requires the configured connection and administrator enablement. It respects the caller's SCM permissions and supplies code search to Rovo Chat, Rovo Agents, Teamwork Graph CLI, and MCP. Search alone does not guarantee full-file text; MCP's separate `getCodeFile` contract is the relevant retrieval candidate. [Atlassian Code context](https://support.atlassian.com/organization-administration/docs/what-is-code-context/) [MCP tool catalog](https://support.atlassian.com/atlassian-ai-gateway/docs/supported-tools/)

The relay only selects the rendered chat's GitHub source filter. It does not inspect connector eligibility, indexing, permissions, an upstream retrieval tool, or downloaded file bytes; its response export reads rendered text and explicitly reports `attachment_bytes_included: false`. [Local source](../cli_anything/rovo/rovo_cli.py) [Local source](../cli_anything/rovo/utils/rovo_backend.py)

**Conclusion:** a Rovo claim that it downloaded a file without showing source text is unverified retrieval. It cannot be repaired by response parsing or duplicate-link cleanup. The host/org's Code context status, repository coverage, indexing state, available GitHub retrieval tools, and any actual download artifact remain unknown.

**Verification gate:** perform a read-only configuration and existing-evidence review with the Rovo integration owner. Check Code context eligibility/enabled state, connected repository and branch coverage, indexing state, caller permissions, and the available code-search or file-retrieval tool output. Do not enable indexing, change grants, or send another Rovo question in this slice.

## Bounded next slice

1. Inspect official access and prior retrieval evidence read-only; prefer official retrieval if it passes the known-file comparison in the improvement plan.
2. If Rovo delegation is needed, check approved A2A host support before expanding browser infrastructure.
3. If the bridge remains necessary, run the actual-host continuity check and attribute the shorter failure before changing any timeout.

The research does not itself authorize policy changes, profile copies, live Rovo questions, installs or credit-consuming actions. Separately authorized local status-only checks and their limited applicability are recorded in [the improvement plan](CONNECTION_IMPROVEMENTS.md#local-live-diagnostic-observation).
