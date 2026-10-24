# Validation status

## Verified new-chat capture (2026-10-24)

A passive observer on the owned tab showed that Rovo's send request names the new conversation in its URL: exactly one `POST {site}/gateway/api/assist/rovo/v1/chat/conversation/{id}/message/stream/sse`, sent about 90 ms after Submit, with the prompt in its body. The ID appeared in no earlier request, and it matched the ID the previous picker comparison, reopen and turn-hash check verified. The request streams the answer and never finishes, so the CLI reads it as it starts. Analytics beacons, read-status updates and browser storage were rejected as sources.

The change passed **302 tests** from source and from the installed wheel, with **8 opt-in local-browser checks skipped** in each, and all 15 packaged files matched source. One synthetic `ask --new` then ran through the installed CLI in normal Chrome:

| Phase | Previous path (same day, two runs) | Send-request capture |
|---|---:|---:|
| Select | 719 to 763 ms | 55 ms |
| Capture | 1,155 to 1,156 ms | 14 ms |

The answer completed with verified continuity and turn count one. A read-only export of the bound ID in the same session returned exactly the synthetic prompt and answer. One question was sent; no submission was retried. Preparation time is not compared because the acceptance run prepared the panel during session startup. These are single observations, not averages.

## Verified follow-up speed (2026-10-24)

Implementation `125d940`, included in published `main` at `34ffca7`, passed the live comparison below through the installed CLI in normal Chrome. Both source and installed-wheel suites passed **302 tests**, with **8 opt-in local-browser checks skipped** in each. The wheel used the declared isolated build requirements, and all 15 packaged files matched source byte for byte.

| Phase | Normal picker | Verified open-chat shortcut | Difference |
|---|---:|---:|---:|
| Attach | 3 ms | 3 ms | 0 ms |
| Prepare | 171 ms | 196 ms | +25 ms |
| Select | 1,240 ms | 33 ms | -1,207 ms |
| Generate | 7,643 ms | 7,222 ms | -421 ms |
| Capture | 11 ms | 14 ms | +3 ms |
| Total | 9,068 ms | 7,468 ms | -1,600 ms |

The shortcut reduced chat-selection time by **97.3%** in this comparison. Total time was **17.6%** lower, but the 421 ms difference in Rovo generation is not attributable to skipping the picker. These are two consecutive observations, not an average or a guarantee for other requests.

Exactly two questions were sent, once each, in one retained connection. The first continued an existing synthetic chat through the picker; the immediate follow-up returned `chat_selection: warm_tab`. Both completed with verified continuity and the same observed conversation ID. Turn count increased by one for each answer; a read-only export confirmed the original history was unchanged and exactly two turns were added. Native Chrome showed the expected answers and an empty composer. No submission was retried.

The successful shortcut confirms that the message ID captured after the first answer still matched at the follow-up check. Longer-term stability, other layouts and invocation from Copilot remain unverified. Synthetic response completion does not establish grounded retrieval or the absence of provider-side effects.

The CLI exited normally, only the test-created tab was closed, and all original tabs remained intact. Private prompts, logs, identifiers and screenshots remain outside the repository. No account details or machine-specific paths are included here.

<a id="current-development-baseline-2026-10-23"></a>

## Earlier development baseline (2026-10-23)

Source `41ca8de`, package version `0.1.0a6`, passed **249 offline tests** against the installed command outside the checkout, with `CLI_ANYTHING_FORCE_INSTALLED=1` and the venv executable directory on PATH. The installed backend matched source byte-for-byte and `git diff --check` passed. An initial invocation had 10 subprocess failures because PATH omitted the CLI; the corrected invocation passed all tests. A normal isolated `pip install --no-deps .` build succeeded with the declared build requirements; the older offline fallback described below is historical.

The following live scenarios passed on `7c5f895` in normal signed-in Chrome. They used three separately authorized questions in total, with no submission retries; read-only exports and saved records supplied the verification:

| Scenario | Additional questions | Verified result |
|---|---|---|
| New chat from an empty welcome screen | 1 | Exact synthetic reply; captured and reopened new ID; one turn; export and saved signature matched |
| Existing conversation to `ask --new` | 1 | Enabled New chat path; distinct new ID with one turn; original conversation unchanged |
| Second turn after CLI restart and owned-tab closure | 1 | Plain `ask` with no `--chat` or `--new` reused the saved ID; two turns with the first unchanged; reply used the prior token without repeating it in the follow-up prompt |

The restart test first encountered a pre-submit startup failure, `Ask Rovo (detached)`. After user-approved restart and window expansion, continuity passed. Subsequent read-only investigation reproduced the narrow-window failure: account verification dismissed Show more before clicking the launcher inside it. Commit `41ca8de` removes that premature dismissal while retaining final menu cleanup and all identity/delivery checks. Its regression failed before the fix; fresh installed startup and another status then passed at the narrow layout without resizing. **No questions were sent after this readiness fix.**

Commit `7c5f895` added private-safe `click_diagnostics` with a fixed control label, allowlisted reason and timeout flag. The reproduced startup failure verified those diagnostics live. The earlier post-readiness pre-submit timeout still lacks its original detailed call log and remains unidentified; it must not be attributed to this startup bug. No automatic click or submission retry was added.

Task-owned diagnostic processes, tabs and build scaffolding were removed; synthetic conversations and request evidence remain private outside Git. These results accept the measured local paths only. Copilot acceptance, grounded retrieval and mini-modal sends remain open. See [the testing runbook](TESTING_RUNBOOK.md) for the repeatable procedure. Earlier sections below retain their candidate-specific historical counts and limits.

## Automatic conversation continuity (2026-10-23)

Commit `bcb1554` adds automatic conversation binding for the same site/session/account, explicit `--new`, verified capture from loaded picker IDs and history checks before follow-up. The final installed candidate passed 205 offline tests outside the checkout with `CLI_ANYTHING_FORCE_INSTALLED=1`; all 12 installed files and three documentation mirror pairs matched source. Use the [development testing runbook](TESTING_RUNBOOK.md) for the repeatable procedure.

Three authorized synthetic turns completed in the owner's normal signed-in Chrome with the same captured conversation ID and visible turn counts of one, two and three. No follow-up supplied `--chat`. The second turn reused the foreground connection; the third used a fresh installed process and reopened the saved chat. The final pre-submit history and persistence refinements were verified offline after these live requests, not by another live submission. The exact pinned isolated build remained unavailable; the wheel used existing setuptools 84.0.0 and wheel 0.48.0.

The initial synthetic “remember” wording unexpectedly created a Rovo memory despite instructions not to use tools. The owner approved removal of that exact test entry; the empty memory list verified deletion. Both disposable test tabs and build scaffolding were removed, while user tabs and chat/request evidence were preserved. Future continuity probes avoid “remember” wording and explicitly prohibit memory writes; a correct marker alone never establishes same-chat continuity.

This earlier run accepted the measured local flows, subject to the final-refinement limit above; the current-baseline checks now add later live evidence. Copilot acceptance, grounded retrieval and mini-modal sends remain open. New-chat capture is bounded to loaded picker rows and stops implicit continuation when its identity/history proof is missing or ambiguous.

## Tab and readiness candidate (local, 2026-10-22)

The existing CLI now creates and binds its own tab in the approved normal Chrome context, opens Ask Rovo and waits for account/panel/composer readiness. It does not inspect or select user-owned Rovo tabs, reload pages, retry submissions or add a browser/dependency. A closed owned tab is replaced only after the existing site-wide unresolved-delivery check. Live testing exposed stale Playwright close events while stdin was idle; draining pending events before checking the bound tab fixed that case, with an offline regression.

The candidate passed 185 offline tests from outside the checkout with `CLI_ANYTHING_FORCE_INSTALLED=1`. All 12 installed source/document files and three documentation mirrors matched the checkout. The pinned isolated build could not run offline because its setuptools version was not cached; the validation wheel used already-cached setuptools 84.0.0 and existing wheel 0.48.0, with no dependency download. Exact pinned-build reproduction remains unverified.

In the user's normal signed-in Chrome, startup opened a fresh tab and prepared a legacy Rovo panel while two other Jira/Rovo panels were open. Repeated status reused that tab and one connection; a synthetic unsent draft in the separate test tab stayed unchanged. Closing the owned panel was followed by automatic reopening without reload. Closing the owned tab was followed by successful replacement and readiness on the same connection. The installed candidate returned exit 0 and `authenticated_ui`; EOF detached once and closed its verified empty tab. A final one-shot status also verified automatic preparation and safe tab cleanup after tightening the final origin check. The separate synthetic draft and disposable comparison tab were removed, leaving the original user conversation intact. Request records were unchanged. No Rovo question, upload or retry was made; private evidence remains outside Git.

This proves the local tab/preparation flows only. It does not diagnose an earlier refresh report from a Copilot run as stale frontend state, prove readiness under Copilot, or expand mini-modal sending/list/export support. Failed or unverified preparation is preserved and reported without reload. Conversation-bearing or uncertain tabs remain open on exit. Use the canonical Copilot setup prompt's two-status test through Copilot; no new tool, permission or installation is implied by local acceptance.

## Local checks

The development baseline passed 20 unit and installed-command tests. They cover destination and identity validation, site locks, durable uncertain delivery, stale response rejection, output bounds, image policy, installed skill discovery, dry-run behavior and command validation. The clean repository passed all 20 tests after a fresh installation on 2026-10-21, with `CLI_ANYTHING_FORCE_INSTALLED=1` and the test process launched outside the checkout. The wheel built successfully and its package files matched the sanitized source. No browser request is made by this suite.

## Explicit Chrome port candidate (0.1.0a4)

Enabled debugging on the local normal Chrome was listening while its `DevToolsActivePort` file was absent (`ENOENT`). Global `--chrome-port PORT` now connects to the verified existing browser's loopback WebSocket without relying on file or HTTP discovery. Default channel discovery remains unchanged. Chrome approval, per-operation binding and delivery checks, immutable connection ownership and no automatic retry/fallback remain in place. No discovery file, replacement browser or browser-policy change is created.

On 2026-10-22, the installed 0.1.0a4 candidate passed all 144 offline tests outside the checkout with `CLI_ANYTHING_FORCE_INSTALLED=1`. All 12 packaged source/document files matched the checkout. New cases cover explicit-port attachment/reuse, one-shot and REPL routing, invalid-port refusal, dry-run without attachment, immutable stream/REPL ports and no endpoint fallback. The initial five explicit-port feature regressions failed before implementation.

The installed candidate then passed two live account-bound status operations in one foreground process: startup status followed by one `["status"]` command. Both returned exit 0 and `readiness: authenticated_ui_read_only`, with `active_generation: null`. Private Playwright connection logs show exactly one connection and one disconnect; no disconnect occurred before stdin closed. The process exited 0, request-record hashes were unchanged and no Rovo question, prompt entry or upload occurred. The task-created tab and empty CLI state directory were removed; evidence stays outside Git.

This accepts persistent read-only inspection on a local Chrome using an explicitly verified port. Mini-modal sends/list/export and generation/attachment/completion evidence remain unverified, as do Copilot acceptance and grounded retrieval. A successful local transport check does not expand those gates.

## Persistent session candidate (0.1.0a3)

The foreground `session` and human REPL retain one lazy approved Chrome connection. Offline regressions cover repeated operation checks, site locks while idle, unresolved delivery before attachment, startup flushing, JSON argv framing, immutable binding, stdin protection, recoverable preparation errors, terminal uncertain sends and timeouts, EOF/signals, no reconnect and cleanup failures. They use in-process Click and synthetic Playwright doubles; no Chrome or Rovo request is made. Focused session regressions were observed failing before implementation, including later startup-schema and nested-REPL fixes. Installed subprocess checks cover doctor, session help and dry-run startup.

On 2026-10-22, the installed 0.1.0a3 candidate passed all 132 offline tests with `CLI_ANYTHING_FORCE_INSTALLED=1`, its executable directory on PATH and the test process outside the checkout. Imports resolved to the installed package; all 12 packaged source/document files and three source mirror pairs matched byte for byte. `git diff --check` passed. Build and egg-info scaffolding was removed; private evidence stayed outside Git. No live browser connection or Rovo submission was attempted.

Direct persistent attachment was not live-accepted for 0.1.0a3; the 0.1.0a4 local read-only result is recorded above. Do not send a diagnostic question, change browser protections or terminate user Chrome to test disconnects. The prior local handshake failure's approval hypothesis remains unconfirmed. Copilot acceptance and mini-modal generation/attachment/completion gates remain open; this lifecycle change does not expand mini-modal operations or automatic MCP eligibility.

## Panel compatibility candidate

The local candidate passed all 87 offline tests after installation on 2026-10-22, with `CLI_ANYTHING_FORCE_INSTALLED=1` and the test process launched outside the checkout. Backend, README and both skill files matched the installed package byte for byte; all source mirrors matched. The package still reports 0.1.0a2, so version alone does not identify the panel-compatibility candidate; record its checkout revision and installed-file parity.

The 49 browser-boundary cases use synthetic Playwright doubles without opening a browser. They cover eligible routes and tab selection, hidden/duplicate/overlapping panel roots, account checks, missing or unusable composers, draft/attachment/generation guards, disabled New chat, navigation and uncertain delivery. Mini-modal cases prove account-bound read-only status with one visible composer, unknown generation and refusal before ask/list/export; they do not prove mini-modal response extraction or safe sending. The initial refusal/guard regressions and eight read-only-status cases were observed failing before their runtime patches. Existing completion and handoff tests still reject stale or incomplete evidence.

A read-only completed-conversation report establishes the mini-modal response-card/message-group structure, but its status label is `Message sent.`, not `Response complete.`. The completion predicate still rejects that acknowledgement. Mini-modal generation, attachment-state handling, completion transitions and Copilot acceptance remain open. Status returns `readiness: authenticated_ui_read_only` and `active_generation: null`; it must not trigger a live question or a transport switch. Obtain read-only evidence of generation and a reliable terminal transition before implementing response handling or an empty-chat bypass. No live request was sent for this candidate.

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

These checks used incremental installs on macOS. The final development build also passed an installed draft-preservation check. Raw transcripts, screenshots, account IDs, repository names, test-site configuration and local paths are deliberately excluded from this repository.

## Open acceptance gates

Grounded GitHub retrieval, structured citations, multiple-image live tests, upload error variants, older history pagination, uncertain-delivery reconciliation, actual Copilot invocation, other operating systems, headless operation and end-to-end token or billing savings remain unverified or unimplemented. The standalone guide's measured core-skill text reduction is a narrower claim.

Live calls consume Rovo credits. An earlier development run exhausted its allowance; that historical observation does not establish the current balance. Each new live test requires authorization and available allowance. Documentation review does not authorize questions. A finished CLI response is not a passing code-retrieval result.

## Chrome connection diagnostic regression

The reported `DevToolsActivePort file not found` failure occurs before attachment, authentication checks or Rovo submission. The bundled Playwright discovery reads the default Chrome data location for the CLI's OS/user. Its multiline setup hint was lost when the adapter kept only the first error line. The adapter now returns a stable error code and explicit setup steps while suppressing the profile path; the README, skill and single setup prompt describe Chrome's supported enable/approve flow and environment limitations.

Two offline regression cases inject this failure at the Playwright connection boundary for status and ask. They verify actionable diagnostics, no submission, no request record and lock release. These tests validate error handling, not any browser's settings.

## MCP fallback development checks

Version 0.1.0a2 adds the skill fallback, packaged reference and local handoff guard. Offline tests cover reservation persistence, cross-session/cross-transport blocking, prompt/account/site/request correlation, stale/incomplete response rejection, output caps, dry-run behavior and installed begin/finish commands. These are local protocol tests with synthetic observations, not proof that a real Copilot MCP session can reach Rovo. No live Rovo prompts were submitted for this change.

The full suite passed 38 tests after installing 0.1.0a2, with the installed-command test process launched outside the checkout. Source/packaged skill parity and reference resolution passed. The generic Codex skill validator rejects the existing `disable-model-invocation` field; it was retained because [VS Code explicitly supports it](https://code.visualstudio.com/docs/agent-customization/agent-skills) for slash-only invocation. A separate YAML check validated the Copilot frontmatter and local reference paths; this does not prove live Copilot discovery.

An independent source-level behavioral review covered seven scenarios: eligible fallback, existing draft, direct ask timeout, new-profile requirement, lost MCP click result, an unresolved direct request under another session, and stale completion evidence. It found no routing blocker and confirmed stop/no-resend behavior for the unsafe cases. This was reasoned review, not a live MCP tool execution.
