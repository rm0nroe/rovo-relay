# Validation status

## Tab and readiness candidate (local, 2026-10-22)

The existing CLI now creates and binds its own tab in the approved normal Chrome context, opens Ask Rovo and waits for account/panel/composer readiness. It does not inspect or select user-owned Rovo tabs, reload pages, retry submissions or add a browser/dependency. A closed owned tab is replaced only after the existing site-wide unresolved-delivery check. Live testing exposed stale Playwright close events while stdin was idle; draining pending events before checking the bound tab fixed that case, with an offline regression.

The candidate passed 185 offline tests from outside the checkout with `CLI_ANYTHING_FORCE_INSTALLED=1`. All 12 installed source/document files and three documentation mirrors matched the checkout. The pinned isolated build could not run offline because its setuptools version was not cached; the validation wheel used already-cached setuptools 84.0.0 and existing wheel 0.48.0, with no dependency download. Exact pinned-build reproduction remains unverified.

In the user's normal signed-in Chrome, startup opened a fresh tab and prepared a legacy Rovo panel while two other Jira/Rovo panels were open. Repeated status reused that tab and one connection; a synthetic unsent draft in the separate test tab stayed unchanged. Closing the owned panel was followed by automatic reopening without reload. Closing the owned tab was followed by successful replacement and readiness on the same connection. The installed candidate returned exit 0 and `authenticated_ui`; EOF detached once and closed its verified empty tab. A final one-shot status also verified automatic preparation and safe tab cleanup after tightening the final origin check. The separate synthetic draft and disposable comparison tab were removed, leaving the original user conversation intact. Request records were unchanged. No Rovo question, upload or retry was made; private evidence remains outside Git.

This proves the local tab/preparation flows only. It does not diagnose the earlier Copilot-host refresh complaint as stale frontend state, prove readiness on that device, or expand mini-modal sending/list/export support. Failed or unverified preparation is preserved and reported without reload. Conversation-bearing or uncertain tabs remain open on exit. Use the canonical Copilot setup prompt's two-status test on the actual Copilot host; no new tool, permission or installation is implied by local acceptance.

## Local checks

The development baseline passed 20 unit and installed-command tests. They cover destination and identity validation, site locks, durable uncertain delivery, stale response rejection, output bounds, image policy, installed skill discovery, dry-run behavior and command validation. The clean repository passed all 20 tests after a fresh installation on 2026-10-21, with `CLI_ANYTHING_FORCE_INSTALLED=1` and the test process launched outside the checkout. The wheel built successfully and its package files matched the sanitized source. No browser request is made by this suite.

## Explicit Chrome port candidate (0.1.0a4)

Enabled debugging on the local normal Chrome was listening while its `DevToolsActivePort` file was absent (`ENOENT`). Global `--chrome-port PORT` now connects to the verified existing browser's loopback WebSocket without relying on file or HTTP discovery. Default channel discovery remains unchanged. Chrome approval, per-operation binding and delivery checks, immutable connection ownership and no automatic retry/fallback remain in place. No discovery file, replacement browser or browser-policy change is created.

On 2026-10-22, the installed 0.1.0a4 candidate passed all 144 offline tests outside the checkout with `CLI_ANYTHING_FORCE_INSTALLED=1`. All 12 packaged source/document files matched the checkout. New cases cover explicit-port attachment/reuse, one-shot and REPL routing, invalid-port refusal, dry-run without attachment, immutable stream/REPL ports and no endpoint fallback. The initial five explicit-port feature regressions failed before implementation.

The installed candidate then passed two live account-bound status operations in one foreground process: startup status followed by one `["status"]` command. Both returned exit 0 and `readiness: authenticated_ui_read_only`, with `active_generation: null`. Private Playwright connection logs show exactly one connection and one disconnect; no disconnect occurred before stdin closed. The process exited 0, request-record hashes were unchanged and no Rovo question, prompt entry or upload occurred. The task-created tab and empty CLI state directory were removed; evidence stays outside Git.

This accepts persistent read-only inspection on the local development Chrome using an explicitly verified port. Mini-modal sends/list/export and generation/attachment/completion evidence remain unverified, as do Copilot-host acceptance and grounded retrieval. A successful local transport check does not expand those gates.

## Persistent session candidate (0.1.0a3)

The foreground `session` and human REPL retain one lazy approved Chrome connection. Offline regressions cover repeated operation checks, site locks while idle, unresolved delivery before attachment, startup flushing, JSON argv framing, immutable binding, stdin protection, recoverable preparation errors, terminal uncertain sends and timeouts, EOF/signals, no reconnect and cleanup failures. They use in-process Click and synthetic Playwright doubles; no Chrome or Rovo request is made. Focused session regressions were observed failing before implementation, including later startup-schema and nested-REPL fixes. Installed subprocess checks cover doctor, session help and dry-run startup.

On 2026-10-22, the installed 0.1.0a3 candidate passed all 132 offline tests with `CLI_ANYTHING_FORCE_INSTALLED=1`, its executable directory on PATH and the test process outside the checkout. Imports resolved to the installed package; all 12 packaged source/document files and three source mirror pairs matched byte for byte. `git diff --check` passed. Build and egg-info scaffolding was removed; private evidence stayed outside Git. No live browser connection or Rovo submission was attempted.

Direct persistent attachment was not live-accepted for 0.1.0a3; the 0.1.0a4 local read-only result is recorded above. Do not send a diagnostic question, approve debugging automatically, change browser protections or terminate user Chrome to test disconnects. The prior local handshake failure's approval hypothesis remains unconfirmed. Copilot-host acceptance and mini-modal generation/attachment/completion gates remain open; this lifecycle change does not expand mini-modal operations or automatic MCP eligibility.

## Panel compatibility candidate

The local candidate passed all 87 offline tests after installation on 2026-10-22, with `CLI_ANYTHING_FORCE_INSTALLED=1` and the test process launched outside the checkout. Backend, README and both skill files matched the installed package byte for byte; all source mirrors matched. The package still reports 0.1.0a2, so version alone does not identify the panel-compatibility candidate; record its checkout revision and installed-file parity.

The 49 browser-boundary cases use synthetic Playwright doubles without opening a browser. They cover eligible routes and tab selection, hidden/duplicate/overlapping panel roots, account checks, missing or unusable composers, draft/attachment/generation guards, disabled New chat, navigation and uncertain delivery. Mini-modal cases prove account-bound read-only status with one visible composer, unknown generation and refusal before ask/list/export; they do not prove mini-modal response extraction or safe sending. The initial refusal/guard regressions and eight read-only-status cases were observed failing before their runtime patches. Existing completion and handoff tests still reject stale or incomplete evidence.

A read-only completed-conversation report establishes the mini-modal response-card/message-group structure, but its status label is `Message sent.`, not `Response complete.`. The completion predicate still rejects that acknowledgement. Mini-modal generation, attachment-state handling, completion transitions and Copilot-host acceptance remain open. Status returns `readiness: authenticated_ui_read_only` and `active_generation: null`; it must not trigger a live question or a transport switch. Obtain read-only evidence of generation and a reliable terminal transition before implementing response handling or an empty-chat bypass. No live request was sent for this candidate.

## Recorded live checks

| Capability | Result |
|---|---|
| Text prompts | Exact requested markers returned through the installed command |
| One PNG | Correctly identified three colors not named in the prompt |
| GitHub source selection | Off/on selection verified in the chat UI |
| Known GitHub file | Retrieval failed on the development site; cause unconfirmed |
| Conversation follow-up | Reopened an observed ID and answered about the prior image without re-uploading |
| Loaded history | Listed conversations with observed IDs and titles |
| Transcript export | Returned correctly separated visible user/assistant text |
| Draft preservation | Expected refusal before submission; the draft remained unchanged |

These checks used incremental installs on one macOS development host. The final development build also passed an installed draft-preservation check. Raw transcripts, screenshots, account IDs, repository names, test-site configuration and local paths are deliberately excluded from this repository.

## Open acceptance gates

Grounded GitHub retrieval, new-chat ID capture, structured citations, multiple-image live tests, upload error variants, older history pagination, uncertain-delivery reconciliation, actual Copilot invocation, other machines/OS versions, headless operation and measured token savings remain unverified or unimplemented.

Live calls consume Rovo credits. The development allowance was exhausted; no further Rovo prompts are part of the repository preparation. A finished CLI response is not a passing code-retrieval result.

## Chrome connection diagnostic regression

The reported `DevToolsActivePort file not found` failure occurs before attachment, authentication checks or Rovo submission. The bundled Playwright discovery reads the default Chrome data location for the CLI's OS/user. Its multiline setup hint was lost when the adapter kept only the first error line. The adapter now returns a stable error code and explicit setup steps while suppressing the profile path; the README, skill and single setup prompt describe Chrome's supported enable/approve flow and environment limitations.

Two offline regression cases inject this failure at the Playwright connection boundary for status and ask. They verify actionable diagnostics, no submission, no request record and lock release. These tests validate error handling, not the target machine's browser settings. Authenticated acceptance on that machine remains pending.

## MCP fallback development checks

Version 0.1.0a2 adds the skill fallback, packaged reference and local handoff guard. Offline tests cover reservation persistence, cross-session/cross-transport blocking, prompt/account/site/request correlation, stale/incomplete response rejection, output caps, dry-run behavior and installed begin/finish commands. These are local protocol tests with synthetic observations, not proof that a real Copilot MCP session can reach Rovo. No live Rovo prompts were submitted for this change.

The full suite passed 38 tests after installing 0.1.0a2, with the installed-command test process launched outside the checkout. Source/packaged skill parity and reference resolution passed. The generic Codex skill validator rejects the existing `disable-model-invocation` field; it was retained because [VS Code explicitly supports it](https://code.visualstudio.com/docs/agent-customization/agent-skills) for slash-only invocation. A separate YAML check validated the Copilot frontmatter and local reference paths; this does not prove live Copilot discovery.

An independent source-level behavioral review covered seven scenarios: eligible fallback, existing draft, direct ask timeout, new-profile requirement, lost MCP click result, an unresolved direct request under another session, and stale completion evidence. It found no routing blocker and confirmed stop/no-resend behavior for the unsafe cases. This was reasoned review, not a live MCP tool execution.
