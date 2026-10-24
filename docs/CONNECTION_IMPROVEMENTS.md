# Connection reliability: bounded improvement plan

## Findings and scope

Primary-source research is recorded in [Connection findings](CONNECTION_FINDINGS.md). Chrome's maintainers recommend longer connection sessions, not persistent approval. Code context is a separate capability whose availability must be checked in the target organization.

Original research baseline: `3e914a7`; current code/evidence review: `41ca8de` on 2026-10-23. The CLI reuses one Chrome connection inside `session` and the human REPL. `BrowserConnection.get()` attaches once; EOF, terminal errors and process shutdown detach. The skill requests a retained foreground process, then instructs the agent to close stdin when finished. It does not establish reuse across separate skill invocations or expose a local connection service. Verified conversation state now persists across process restarts; browser connections and approval do not.

The supplied Copilot-host reports describe separate processes closing between attempts. That explains new attachment attempts, not every failed handshake. The CDP attachment timeout is 20 seconds; a shorter reported failure may originate in Playwright startup, the caller's deadline or another connection failure. Elapsed time alone does not identify the cause.

The reported internal repository test completed through the bridge, but Rovo described a file-download result without source contents. That explanation is not independently inspected connector evidence. The bridge reads the rendered response; it cannot repair missing upstream file contents. Keep response completion and retrieval assessment separate.

The initial diagnostics scope excludes live questions, uploads and extra usage. Local testing was subsequently authorized where the local Rovo is sufficiently comparable; matching visible controls alone does not establish matching connector access or host behavior. Browser-policy changes and uncertain-submission retries remain excluded. Keep mini-modal ask/list/export blocked. Reuse the existing request records, locks, completion predicate and per-operation account/tab checks.

## Shipped: attachment and click diagnostics

Commit `a224aa3` shipped the shared `BrowserConnection.get()` diagnostic changes:

- Flushes one fixed, private-data-free notice to stderr immediately before a new CDP attachment, without progress records in the JSON command stream or a repeated notice on reuse. Whether Copilot displays streamed stderr before command completion remains a host-side check.
- Includes `attachment_phase` and the configured `attachment_timeout_ms` in sanitized failure JSON. It distinguishes `runtime_startup` from `browser_attachment` without claiming an approval, denial or detailed WebSocket phase. Elapsed time still includes startup; the configured timeout applies only to the CDP call.
- Preserves error codes, fallback eligibility, timeout values, terminal behavior and durable delivery state. This improves diagnosis; it does not eliminate approval prompts or resolve the external failure.

Files: `utils/rovo_backend.py`, `tests/test_session.py`, both README copies, `docs/COPILOT_SETUP_PROMPT.md`, and `tests/TEST.md`. Three offline regressions cover notice ordering/flush/reuse and the two failure phases through the existing session interface.

Commit `7c5f895` subsequently routed clicks through `click_control`, reporting private-safe control/reason/timeout diagnostics without retries. Commit `41ca8de` fixes the reproduced narrow-window startup failure by leaving Show more open through the Ask Rovo click, with final cleanup preserved. Its installed suite passed 249 tests and startup plus another status passed in narrow normal Chrome. No questions were sent for the fix; the existing two-turn request record was unchanged. [Current validation](VALIDATION.md#current-development-baseline-2026-10-23)

Earlier in the same day's acceptance work, three authorized questions verified empty-screen creation, an existing-chat-to-new-chat switch and automatic second-turn continuation after CLI restart. Distinct/same IDs, exports and saved signatures established the expected boundaries. Those send checks ran at `7c5f895`; the final overflow fix was verified offline and with read-only status. Copilot-host, mini-modal-send and grounded-retrieval acceptance remain open.

## Next gate: reuse across skill invocations

Run this bridge-specific gate if official access does not cover the required workflow. First verify the actual Copilot host, without a Rovo question:

1. In the actual Copilot host, start one approved foreground session, collect its startup status and retain its process and streams.
2. In a later skill invocation/user turn, submit only `status` to that same process. These two status checks must share one process. Keep private evidence of process identity, retained handles, one attachment, no intervening disconnect and no second approval request. A matching `--session` argument alone does not prove process continuity.
3. Close stdin explicitly and verify clean detachment without closing user tabs.

If handles survive, update the canonical skill and packaged mirror to define an explicit working-session lifetime: reuse the known healthy owner, recheck status before work, and close on explicit stop, session completion or terminal failure. The existing CLI loop already supports additional commands after successful responses. Readiness still does not authorize a new question.

If handles do not survive, document the host limitation before adding code. A separately scoped local owner would reuse `BrowserConnection` and `operate`, serialize commands and bind site/account/port. Its minimum design must include access-controlled local IPC, explicit start/stop, bounded idle cleanup, per-command fresh guards, and crash/disconnect handling that preserves uncertain delivery. Do not add an unauthenticated TCP service, automatic reconnect or a second delivery-state store. No daemon is included in the current implementation.

## Diagnose the shorter timeout before changing it

Compare one existing failed trace with a successful trace from the same installed revision and environment. Record caller start/deadline/termination, configured CDP budget, whether the attachment notice appeared, and any returned phase/elapsed fields. Keep all raw evidence outside Git. If the process is killed before it can emit JSON, record the missing receipt rather than treating it as a known Chrome denial.

Only after locating the limiting layer should a bounded caller or attachment-budget change be proposed. Verify delayed approval synthetically, preserve one attachment attempt and prove that no question is queued before successful readiness. Never use `ask --timeout` as an attachment-timeout setting: it is the response-wait budget.

## Investigate source retrieval independently

### First gate: official access

Prefer an approved official data interface when it meets the need. MCP v2's `getCodeFile` is the first documented full-file candidate; TWG command coverage must be checked rather than assumed. For delegation to Rovo itself, assess A2A separately. The capability comparison and documentation corrections are in [Connection findings](CONNECTION_FINDINGS.md#official-alternatives-checked-on-2026-10-22).

1. Inspect the target site's existing Code context eligibility, GitHub connection and repository scope, indexing status, linked identity and caller permissions. Record evidence privately. Stop at any missing permission; do not enable features or change grants.
2. In an already approved MCP v2 connection, inspect accessible resources and authenticated identity, then discover `getCodeFile` and `searchCode`. Verify the intended site and read-only tool schema. Code tools require OAuth; a working Jira API-token connection is insufficient evidence. For TWG, inspect the installed version's help and auth status instead.
3. Select one known-readable UTF-8 source file at an immutable commit. Save repository, path, commit, expected byte count and SHA-256 from the source Git blob outside this repository. The dirty working-tree copy and a moving branch name are not valid reference bytes.
4. Once usage and source-disclosure scope are authorized, fetch that exact file once through the discovered read tool. Preserve the tool receipt and decoded content privately. Check repository/path/revision, completeness and equality against the reference. Record any encoding or newline normalization explicitly; excerpts, links, summaries and truncated output do not pass full-file acceptance. Do not silently retry or fall back to a chat question.
5. If it passes, use the official interface for code retrieval and leave connection-service work out of scope. If unavailable, report the exact access or capability gap. A failed permission check does not show that a browser wrapper can retrieve the missing content.

No target-organization acceptance is established by the published catalog. Existing local status receipts also cannot establish Copilot process lifetime or explain that host's shorter failure. Those gates need the actual host and its traces.

Use existing response/tool evidence and a read-only configuration inspection to check Code context eligibility, enabled state, repository coverage, indexing state and available code-search tools. Do not enable indexing, change grants or submit another diagnostic question. If the existing download result is inspectable, determine whether it contains source text, an artifact reference or metadata only; redact private identifiers from any report.

Atlassian documents Code context as separately enabled and describes the `search-code` path. This is a capability to check, not proof it is available here. Missing upstream text should be investigated with the Rovo integration owner. Do not scrape around trust blocks, invent function content or classify retrieval success from model wording.

Structured source-link extraction is a later slice only after an existing response supplies trustworthy structural evidence for its anchors. An observed UI URL is not automatically a verified code citation. Text de-duplication cannot fix absent source content.

## Acceptance and delivery

Observe each regression failing before its patch. Run the affected tests, then the applicable installed suite outside the checkout with `CLI_ANYTHING_FORCE_INSTALLED=1` and the installed executable directory on PATH. Check packaged/source parity, documentation mirrors and `git diff --check`. Record which environment was installed; the current development venv contains the verified fix. Preserve logs outside Git and remove task-created build/install/test scratch. Commit and push only with user authorization. See the [testing runbook](TESTING_RUNBOOK.md).

Offline success establishes the diagnostic behavior, not cross-invocation host persistence, the cause of a real handshake failure or GitHub content retrieval.

### Historical attachment-diagnostic verification (2026-10-22)

The isolated installed diagnostics candidate passed all **164 offline tests**, including the three new regressions. Tests ran outside the checkout with installed-command enforcement. All 12 packaged files matched source, all three documentation/skill mirror pairs matched, both command names passed `doctor`, and `git diff --check` passed. The working installation was unchanged. Build metadata, build output, the isolated install and test scratch were removed; wheel, logs and verification receipts remain outside Git.

The attachment diagnostics were committed and pushed in `a224aa3`; later shipped fixes and their current counts are summarized above. Copilot-host installation and live acceptance remain pending. Official-access verification precedes new bridge infrastructure; a service or timeout change still depends on the Copilot evidence above.

### Local live diagnostic observation

This section records the 2026-10-22 attachment checks. The later conversation and overflow checks are summarized above and in [Validation status](VALIDATION.md).

The local normal-Chrome Rovo exposes the Sidebar controls visible in the supplied Copilot-host screenshots. This supports local connection-path testing, but does not prove identical service builds, organization capabilities, code access or Copilot behavior.

One status-only attempt using the exact tested source and an independently verified existing normal-Chrome endpoint emitted the notice before attachment, then failed with `chrome_connection_failed`, `attachment_phase: browser_attachment`, `attachment_timeout_ms: 20000`, and `attachment_elapsed_ms: 20293`. The Playwright trace showed a connection attempt followed by disconnect at 20 seconds; no established connection was recorded. The result was `submission_state: not_attempted`, `retry_safe: true`, exit code 1. No second status or Rovo question was sent, and existing delivery records were unchanged. This validates the live failure diagnostics, not the reason Chrome did not attach. Approval visibility and receipt were not observed.

After the user confirmed readiness to approve Chrome, a fresh status-only session attached successfully at about 13 seconds. Its startup status and a later `status` command through the same retained process both returned `authenticated_ui`, `active_generation: false`, `submission_state: not_attempted` and exit code 0. The trace contained exactly one attachment notice, one connection attempt, one established connection and one disconnect after explicit EOF; the process exited 0. Private process/stream evidence was retained. The empty composer and disabled Submit button were checked afterward, the original floating view was restored, and the task-created tab was closed. Existing delivery records remained unchanged.

This proves local connection reuse across separate Codex tool calls, not separate Copilot skill invocations. It also demonstrates that a successful local attachment can take longer than seven seconds; attributing the remote failure still requires that caller's trace. No live Rovo question was sent. Identical service builds, organization code access and full-file retrieval remain unverified.

References checked during the preceding investigation: [Chrome's maintainers recommend longer-lived connections](https://github.com/ChromeDevTools/chrome-devtools-mcp/issues/825), [Chrome auto-connect and approval](https://developer.chrome.com/docs/devtools/agents/use-cases/auto-connect), [Atlassian Code context](https://support.atlassian.com/organization-administration/docs/what-is-code-context/).
