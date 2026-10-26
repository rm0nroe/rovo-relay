# Validation status

## Verified approval without Quartz (2026-10-26)

Goal: guarded approval without extra Python packages. The helper ran on system `/usr/bin/python3` and needed Quartz, which macOS does not ship, so without a hand-installed pyobjc it failed preflight with `dependencies`. Quartz only found the prompt window, and reading other apps' window names also needs Screen Recording.

Change: the helper finds the prompt through System Events, like the press it already made, so it needs only Accessibility (plus Automation of System Events) for the app running the CLI. It runs on the CLI's own interpreter; `allow.sh` is removed.

Live, 0 questions: a one-shot `status` with `--approve-chrome-prompt`, while a watcher polled the new lookup. The prompt appeared as a sheet on the front Chrome window, disappeared, and `status` returned `authenticated_ui`; no CLI window or debugging client remained. The minimal update check then ran exactly as written, 2 questions, from a fresh regular install: the broker took its port from `lsof` (Chrome had written no `DevToolsActivePort`) and was approved with no click; the multi-line new chat, the timed-out follow-up (exit 3, empty `partial_answer`), reconcile (`orbit-5826`), list (complete) and export (complete, 4 messages) all passed through it, and SIGTERM removed the socket with no CLI window left. It also showed that a timeout result carries `next: stop`, so the check's step 3 now expects that. Offline: 400 passed from source and from the installed wheel. Run by VS Code Copilot with no Quartz installed, the same check passed all five steps through a broker Copilot started with `--approve-chrome-prompt`.

## Verified out-of-sight operation (2026-10-24)

Goal: nothing the CLI does should be visible. Three things were: a 40 by 886 pixel strip of the CLI's window at the left screen edge, Chrome's "Allow remote debugging?" prompt with the pointer moving and Chrome pulled to the front on every new connection, and CLI windows left behind after timeouts.

Probes, 0 questions:

| Probe | Result |
|---|---|
| CDP `Target.createTarget` with `hidden: true` | Created, but as target type `other`; Playwright drives only pages, so it is unusable here |
| Window placement on a 1512 by 982 display | macOS keeps 40 px of any window on screen, and Chrome's minimum window is 626 by 469. Bottom-right at minimum size leaves 40 by 109 px, with the page still rendering (122 frames/s at a 1440 by 900 viewport) and a click in 116 ms |
| Accessibility press of the prompt's buttons (System Events, a sheet on the front Chrome window) | Cancel cleared a stale prompt; Allow approved a live attach in 0.34 s with the pointer and the front app unchanged |

Changes: the window is parked bottom-right at minimum size with a pinned 1440 by 900 viewport; the approval helper presses Allow through Accessibility (every ownership and dialog check is kept; `cliclick` is no longer needed); `rovo-relay-cli broker` holds one approved connection and serves one-shot commands of the same user over an owner-only socket; reconcile always opens a fresh tab, because Rovo does not refetch a chat in a tab that already loaded it (found live through the broker: reconcile saw history from before its own send and refused with `prompt_missing`); and exit cleanup closes the CLI's tab unless an unsent draft or attachment remains.

Live, installed candidates, 7 questions:

| Step | Result |
|---|---|
| Broker start | One prompt, approved with 0 pointer moves and no front-app change; socket mode `srw-------` |
| Through the broker: status, a follow-up ask, a timed-out ask, reconcile, export | 0 prompts, 0 pointer moves, the CLI window only in the corner; `status` 2.3 s instead of a fresh attach. Reconcile first failed (stale tab, above), then after the fix proved both pending answers |
| A second client while the broker runs | Refused by the approval guard (another client present), as designed |
| A tab closed while Rovo was still generating (`Stop generating` visible), then reconcile 45 s later | The full answer (eight numbered sentences and the final word) was in Rovo's data |
| One-shot `ask --timeout 1` without a broker | Exit 3, no CLI window left on screen; reconcile 30 s later proved the full answer |
| Broker stopped by SIGTERM or idle timeout | Socket removed, no CLI window left on screen |

Measurement note: macOS keeps an off-screen record for a closed window; count only on-screen windows (`kCGWindowListOptionOnScreenOnly`).

Offline: 398 passed and 16 opt-in skipped; 414 passed with `ROVO_DOM_CHECK=1`. Not possible: a fully windowless CLI in the real Chrome profile. Not verified: a display arrangement where the bottom-right corner falls on another monitor.

## Verified history page order (2026-10-24)

When a chat's history arrives in several pages, the CLI used to place each cursor page before the earlier ones, assuming it held older messages. That was never observed. Had Rovo paged the other way, export would have returned scrambled blocks marked `complete`, and reconcile could have matched a repeated prompt's earlier copy and returned its old answer (reproduced offline: exit 0 with the old answer). Pages are now ordered by Rovo's own `time_created`, in whichever direction they arrive. Pages whose times overlap, or that lack times, make export fall back to the page (`loaded_only`) and reconcile report `history_incomplete`. A single page needs no timestamps and is unchanged. A reply-link check was considered and dropped: `parent_message_id` is null on every message.

Read-only scan, 0 questions: all 31 chats in the account fit in one page (largest 60 messages); every message has `time_created`, ascending; `parent_message_id` is always null. The messages endpoint ignores `limit`, `pageSize`, `size` and six other page-size parameters.

Live, installed candidate, 21 questions:

| Step | Result |
|---|---|
| 20 `--chat` follow-ups in 4 sessions (turns 31 to 50) | All completed with the right answer and verified continuity; a page probe after each batch still showed one page (70, 80, 90, 100 messages, `hasNext: false`) |
| `chat export` of the 100-message chat | `coverage: "complete"`, 100 messages, roles alternate, answers in order |
| Repeat of turn 50's prompt with `--timeout 1` | Exit 3 `timeout`, `turns_before: 50`, empty `partial_answer` |
| `reconcile` | Exit 0; proved by the new answer's message ID (the last message), not the earlier copy's; `status` then unblocked |

Offline: 383 passed and 16 opt-in skipped; 399 passed with `ROVO_DOM_CHECK=1`; installed 383 with 16 skipped; 15 packaged files and 4 mirrors match. Still unverified live: a chat that actually pages.

## Verified timeout partial answer (2026-10-24)

A follow-up that timed out reported the previous turn's answer as `partial_answer` (seen live twice). The in-page read took the answer from the panel's last answer card. Rovo renders the new turn's group, with its message ID, before that turn's own card, so the last card was still the previous answer. The read now takes the last group's own cards, as the turn signature already did. A snapshot whose last group is not yet this turn (no new count or message ID, or another prompt) reports no partial answer. Completion is unchanged: it already required a new turn and a matching prompt.

Live, installed candidate, 2 questions. On the first candidate, which only had the Python-side guard, a timed-out `--chat` follow-up still returned the previous answer; that is how the card-less new group was found. On the final candidate, the same kind of follow-up with `--timeout 1` exited 3 with `partial_answer` empty, and `reconcile` then proved and returned the real answer. `status` was then unblocked.

Offline: 378 passed and 16 opt-in skipped; 394 passed with `ROVO_DOM_CHECK=1`; installed 378 with 16 skipped; 15 packaged files match.

## Verified multi-line prompts (2026-10-24)

Any prompt with a line break was refused before Submit (`Target or draft changed before submission`, `not_attempted`, nothing sent). Rovo's editor turns each line of the filled text into a paragraph, so the composer's text gains blank lines (and a trailing break) and never equalled the prompt. The rendered turn shows the same blank lines, so completion and the turn signature would also have missed it. All of these comparisons now use one rule (`state.plain`): non-blank lines, spaces collapsed. That rule also covers the prompt hash and Rovo's stored text, where an ADF hard break now counts as a line break. A draft whose words changed is still refused.

Live, installed candidate, 1 question. A three-line prompt with a blank line, sent as an explicit `--chat` follow-up with `--timeout 1`: exit 3 `timeout`, `turns_before: 2` from Rovo's data, the hash of the normalized prompt saved. `status` then said `next: reconcile`, and `reconcile` exited 0 with Rovo's own data proving delivery. `status` was then unblocked.

Offline: 376 passed and 14 opt-in skipped; 390 passed with `ROVO_DOM_CHECK=1`; installed 376 with 14 skipped; 15 packaged files and 4 mirrors match.

## Verified guarded reconcile (2026-10-24)

An uncertain attempt (`attempted_unknown`) blocks every send on the site, and until now only a manual record edit could lift it. `reconcile` is the guarded way out. It never sends. Before Submit, an ask now saves the prompt's SHA-256 and the chat's turn count from Rovo's own data (`turns_before`; never the virtualized page's count, so it is null when that data is missing). A new chat that times out also saves the chat ID named by its one observed send. `reconcile` opens that chat in its own tab, reads Rovo's `messages` data and lifts the block only if the history is complete, the prompt hash matches exactly one human turn after `turns_before`, and a non-empty answer follows. A prompt asked earlier in the same chat therefore cannot pass for this attempt. On success the record becomes `completed` / `observed_submitted` / `continuity_status: unavailable` and keeps the original under `reconciled.original`. Anything else changes nothing and reports `reconcile_reason`. A blocked result says `reconcilable: true` and `next: reconcile` only for this session's own provable record.

Live, installed candidate, 2 questions:

| Step | Result |
|---|---|
| `reconcile` on a session with a completed record | Exit 1, `reconcile_not_needed`, no Chrome attachment |
| New-chat ask with `--timeout 1` | Exit 3 `timeout`; record kept the chat ID from the send, the prompt hash and `turns_before: 0` |
| `status` on that session | Exit 4 `blocked`, `reconcilable: true`, `next: reconcile` |
| `reconcile` | Exit 0; Rovo's data proved delivery; the answer returned; record completed with the original kept; `next: new_or_inspect` |
| `status` again | Exit 0, no block. The window left by the timed-out ask was closed; the reconcile and status tabs closed themselves |
| Continued chat: explicit `--chat` follow-up with `--timeout 1` | Exit 3 `timeout`; `turns_before: 1` taken from Rovo's data; `status` said `next: reconcile` |
| `reconcile` | Exit 0; the prompt matched once after the first turn; answer returned; `status` then unblocked |

Offline: 372 passed and 13 opt-in skipped; 385 passed with `ROVO_DOM_CHECK=1`; installed 372 with 13 skipped. Multi-paragraph prompts were verified later; see [Verified multi-line prompts](#verified-multi-line-prompts-2026-10-24). Not reconcilable by design: records written before this change, MCP reservations, a new chat whose send was not seen exactly once (for example an error after Submit), and another session's record.

## Verified long chats (2026-10-24)

A synthetic chat was built to 30 turns, 30 Rovo questions in all. Findings:

- Rovo's chat panel is **virtualized**: it keeps about 4 to 5 turns on the page, even after scrolling to the top (which shows the first turn). Counting the page undercounts any chat longer than that.
- Rovo's `messages` response held the whole chat in one response at 30 turns (60 items, `hasNext: false`), oldest first, user text as ADF and answers as markdown, each with a message `id`. The page shows the assistant message `id` on each turn.
- Reopening a chat in the same tab serves Rovo's cache: no new `messages` fetch.

That broke three things, all now fixed. Export said `coverage: "complete"` while returning only the turns on the page. An automatic follow-up on a chat past about 5 turns refused with `conversation_changed`. And an ask on a long chat timed out after Rovo had answered: the rendered response count never grew, because the panel dropped an old turn as the new one appeared. The CLI now:

- builds export from Rovo's message data in its own tab (text only, roles mapped to user/assistant, deduplicated by message `id`);
- counts turns from that data, accepts a page showing 1 to that many turns, and adds each verified turn to the tab's copy because Rovo does not refetch;
- treats a last-turn message `id` the chat did not have before submit as new-turn evidence, alongside a rising count;
- applies the same 1-to-N rule to warm-tab reuse and exit cleanup.

The timeout left one synthetic test record as `attempted_unknown`, which blocks the whole site. Rovo's data showed that prompt exactly once, with its answer. With the owner's approval, only that record was reconciled to completed (`continuity_status: unavailable`); the original is kept in private evidence. Nothing was resent.

Live, installed candidate:

| Step | Result |
|---|---|
| Explicit `--chat` ask at turn 12 | Completed and verified (completion by new message `id`) |
| Automatic follow-ups, turns 13 to 30, four sessions | All verified. Each fresh process reopens through the picker; later asks use `warm_tab` (select 20 to 48 ms instead of about 1 s) |
| Exit after long-chat asks | Tab closed; no CLI window left |
| `chat export` of the 30-turn chat | `coverage: "complete"`, all 60 messages in exact order with correct roles |

Unverified: a chat larger than one Rovo response. If Rovo pages it, the CLI scrolls up to load older pages and keeps `loaded_only` until Rovo reports the end; the order of merged pages is assumed. Offline: 345 passed and 13 opt-in skipped; 358 passed with `ROVO_DOM_CHECK=1`; installed 345 with 13 skipped.

## Verified history paging (2026-10-24)

Read-only observation, 0 questions: Rovo's list fetches `GET .../chat/conversations?limit=25`, then prefetches `limit=75` with a cursor, about 100 chats in all. The panel renders only the first 25 rows until it is scrolled. Opening a chat fetches `GET .../chat/conversation/{id}/messages`. Both responses carry `items`, `cursor` and `hasNext`.

The CLI now records those responses from its own tab (listening starts before the page loads) and scrolls the list or the chat until `hasNext` is false. A list is `coverage: "complete"` only when every returned chat is rendered. (Export first also counted rendered turns; the long-chat section below replaced that.) Anything else stays `loaded_only`. Scrolling stops at 100 listed chats or 10 seconds and never clicks.

Live, through the installed candidate, 0 questions:

| Step | Result |
|---|---|
| `chat list` | `coverage: "complete"`, 29 chats (the old code listed the 25 rendered rows) |
| `chat export --chat` of the oldest chat | Found through the picker below the first 25 rows; `coverage: "complete"`, 2 messages |

Offline: 324 passed and 11 opt-in skipped; 335 passed with `ROVO_DOM_CHECK=1`; the installed suite passed 324 with 11 skipped.

Both commands first retained their tab, because cleanup could not prove the picker or an exported chat idle. Now a successful list or export (which checks idle before it starts) marks its tab, and exit closes it unless a draft, attachment or response appeared since. Rerun live, 0 questions: list (29, complete) and export (complete) each exited with no retention notice and no CLI window left; the user's tabs were unchanged. Offline: 335 passed and 11 skipped; 346 with `ROVO_DOM_CHECK=1`; installed 335 with 11 skipped.

A live `session` run then found that a list left the conversation picker open, so the next command could not find the composer and stopped before sending (`submission_state: not_attempted`). The list now clicks `Go back to Rovo chat` before it returns. Rerun through the installed candidate, 2 Rovo questions:

| Step | Result |
|---|---|
| Session 1: status, `chat list`, `ask --chat` of the chat at row 29, export | List complete (29); ask verified at turn 2 through the picker below the first 25 rows (select 1.4 s); export complete with all 4 messages |
| Session 2, fresh process: automatic follow-up, then `chat list` | Same chat, verified turn 3 with the correct recalled code; list complete (29) |
| After both sessions | No retention notice and no CLI window; the user's tabs unchanged |

By session 2 the chat had moved to the top of the list, so only session 1 exercised the picker scroll during an ask. Offline: 336 passed and 11 skipped; 347 with `ROVO_DOM_CHECK=1`.

## Verified hidden CLI window (2026-10-24)

The CLI used to open its tab in the user's current Chrome window, which made it the active tab. When the user or another tool switched back, the CLI tab became hidden. Chrome pauses animation frames on hidden pages, and Playwright's click stability check waits for them, so clicks timed out. This is the cause of the startup `Click timed out: Show more` reports, not the capture harness named in an earlier version of this section.

Evidence, without Rovo questions: opening a tab the old way changed the user's visible Jira tab to `hidden`. A CLI page in a minimized window reported `hidden`, ran 0 animation frames in 1.5 s and reproduced `Click timed out: Show more`. The same page in a background window or moved off-screen ran 5 frames in about 40 ms and clicked in 7 to 95 ms.

The CLI now opens its tab in its own unfocused window, moved off-screen but not minimized (macOS keeps a thin sliver visible). A click that times out on a hidden page reports `reason: page_hidden`. At exit it also closes its idle tab when the tab shows exactly the session's last verified answer, so finished chats no longer leave windows behind; drafts, uncertain delivery and unverified content are still retained.

Live, through the installed candidate, 3 Rovo questions:

| Step | Result |
|---|---|
| Startup and status | Ready; attach 4.1 s, prepare 1.1 s |
| `ask --new` with two PNGs | Both uploads confirmed, `image_count: 2`, continuity verified, turn 1; generate 14.4 s |
| Fresh process follow-up | Same chat through the picker (select 973 ms), turn 2 verified; export showed both pairs |
| After both runs | The user's Jira tab stayed `visible`; no CLI tab or window remained |

The first ask's prompt prohibited tools, so Rovo answered from the file names. A third question used neutral names (`img1.png`, `img2.png`) and allowed viewing: Rovo answered `red, blue`, correct and in order (generate 15.1 s), so both images reach the model. Offline: 316 passed and 11 opt-in skipped; 327 passed with `ROVO_DOM_CHECK=1`. Multiple-monitor placement is unverified: a display left of the main one could show the window.

## Verified pre-send read dedupe (2026-10-24)

Before sending, the CLI no longer repeats reads it has just taken. The idle check (composer, draft, attachments, active response) runs again only after a click it has not already checked, and the conversation signature verified during chat selection is reused instead of read again. Every check after the prompt is filled still runs.

| Path | Idle checks | Signature reads | Round trips saved |
|---|---:|---:|---:|
| Follow-up in the open chat | 2 to 1 | 4 to 3 | about 9 |
| Follow-up through the picker | 3 to 2 | 4 to 3 | about 9 |
| Explicit `--chat` | 3 to 2 | 3 to 3 | about 6 |
| New chat, verified empty | 2 to 1 | 1 to 1 | about 6 |
| New chat, clicked | 2 to 2 | 1 to 1 | 0 |

Each round trip costs about 1 to 3 ms, so the saving is tens of milliseconds at most. The counts are asserted by offline tests.

The change passed **311 tests** from source and from the installed wheel, with **11 opt-in local-browser checks skipped** in each; all 322 passed with the opt-in checks enabled. All 15 packaged files matched source. One synthetic automatic follow-up then ran through the installed CLI in a fresh process, so it used the picker: it completed with verified continuity, the expected answer and turn count two. Selection took 1,401 ms, dominated by the picker's own clicks; one sample cannot show a saving this small. One question was sent; no submission was retried.

## Verified in-page completion wait (2026-10-24)

After Submit, the CLI no longer checks for completion every 200 ms. One wait inside the page watches the Rovo panel for changes and returns as soon as the same completion rules hold, or after at most one second so the site and deadline checks still run. The CLI then applies its own completion check to that result before accepting it.

On synthetic HTML in a throwaway headless Chrome, the wait returned a median **1.6 ms** (maximum 3.2 ms, 20 runs) after the page showed a completed turn. The old 200 ms poll noticed completion 0 to 200 ms late, about 100 ms on average.

The change passed **306 tests** from source and from the installed wheel, with **11 opt-in local-browser checks skipped** in each; the 11 opt-in checks also passed when enabled. All 15 packaged files matched source. One synthetic `ask --new` then ran through the installed CLI in normal Chrome and completed with verified continuity, the expected answer and turn count one. Generation took 7,382 ms, against 7,527 ms for the previous single run; that difference is Rovo's own variance and does not measure the saving. One question was sent; no submission was retried. The first startup attempt stopped at Chrome approval before any page action and was not counted.

## Verified new-chat capture (2026-10-24)

A passive observer on the owned tab showed that Rovo's send request names the new conversation in its URL: exactly one `POST {site}/gateway/api/assist/rovo/v1/chat/conversation/{id}/message/stream/sse`, sent about 90 ms after Submit, with the prompt in its body. The ID appeared in no earlier request, and it matched the ID the previous picker comparison, reopen and turn-hash check verified. The request streams the answer and never finishes, so the CLI reads it as it starts. Analytics beacons, read-status updates and browser storage were rejected as sources.

The change passed **302 tests** from source and from the installed wheel, with **8 opt-in local-browser checks skipped** in each, and all 15 packaged files matched source. One synthetic `ask --new` then ran through the installed CLI in normal Chrome:

| Phase | Previous path (same day, two runs) | Send-request capture |
|---|---:|---:|
| Select | 719 to 763 ms | 55 ms |
| Capture | 1,155 to 1,156 ms | 14 ms |

The answer completed with verified continuity and turn count one. A read-only export of the bound ID in the same session returned exactly the synthetic prompt and answer. One question was sent; no submission was retried. Preparation time is not compared because the acceptance run prepared the panel during session startup. These are single observations, not averages.

## Verified follow-up speed (2026-10-24)

Implementation `3fa3e8e`, included in published `main` at `3b7806a`, passed the live comparison below through the installed CLI in normal Chrome. Both source and installed-wheel suites passed **302 tests**, with **8 opt-in local-browser checks skipped** in each. The wheel used the declared isolated build requirements, and all 15 packaged files matched source byte for byte.

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

Source `48677cb`, package version `0.1.0a6`, passed **249 offline tests** against the installed command outside the checkout, with `CLI_ANYTHING_FORCE_INSTALLED=1` and the venv executable directory on PATH. The installed backend matched source byte-for-byte and `git diff --check` passed. An initial invocation had 10 subprocess failures because PATH omitted the CLI; the corrected invocation passed all tests. A normal isolated `pip install --no-deps .` build succeeded with the declared build requirements; the older offline fallback described below is historical.

The following live scenarios passed on `6b4cb0d` in normal signed-in Chrome. They used three separately authorized questions in total, with no submission retries; read-only exports and saved records supplied the verification:

| Scenario | Additional questions | Verified result |
|---|---|---|
| New chat from an empty welcome screen | 1 | Exact synthetic reply; captured and reopened new ID; one turn; export and saved signature matched |
| Existing conversation to `ask --new` | 1 | Enabled New chat path; distinct new ID with one turn; original conversation unchanged |
| Second turn after CLI restart and owned-tab closure | 1 | Plain `ask` with no `--chat` or `--new` reused the saved ID; two turns with the first unchanged; reply used the prior token without repeating it in the follow-up prompt |

The restart test first encountered a pre-submit startup failure, `Ask Rovo (detached)`. After user-approved restart and window expansion, continuity passed. Subsequent read-only investigation reproduced the narrow-window failure: account verification dismissed Show more before clicking the launcher inside it. Commit `48677cb` removes that premature dismissal while retaining final menu cleanup and all identity/delivery checks. Its regression failed before the fix; fresh installed startup and another status then passed at the narrow layout without resizing. **No questions were sent after this readiness fix.**

Commit `6b4cb0d` added private-safe `click_diagnostics` with a fixed control label, allowlisted reason and timeout flag. The reproduced startup failure verified those diagnostics live. The earlier post-readiness pre-submit timeout still lacks its original detailed call log and remains unidentified; it must not be attributed to this startup bug. No automatic click or submission retry was added.

Task-owned diagnostic processes, tabs and build scaffolding were removed; synthetic conversations and request evidence remain private outside Git. These results accept the measured local paths only. Copilot acceptance, grounded retrieval and mini-modal sends remain open. See [the testing runbook](TESTING_RUNBOOK.md) for the repeatable procedure. Earlier sections below retain their candidate-specific historical counts and limits.

## Automatic conversation continuity (2026-10-23)

Commit `60b76b7` adds automatic conversation binding for the same site/session/account, explicit `--new`, verified capture from loaded picker IDs and history checks before follow-up. The final installed candidate passed 205 offline tests outside the checkout with `CLI_ANYTHING_FORCE_INSTALLED=1`; all 12 installed files and three documentation mirror pairs matched source. Use the [development testing runbook](TESTING_RUNBOOK.md) for the repeatable procedure.

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

Grounded GitHub retrieval, structured citations, more than two images, upload error variants, chats larger than one Rovo response (none seen up to 102 messages), session lifetime under Copilot, other operating systems and end-to-end token or billing savings remain unverified or unimplemented. The standalone guide's measured core-skill text reduction is a narrower claim.

Live calls consume Rovo credits. An earlier development run exhausted its allowance; that historical observation does not establish the current balance. Each new live test requires authorization and available allowance. Documentation review does not authorize questions. A finished CLI response is not a passing code-retrieval result.

## Chrome connection diagnostic regression

The reported `DevToolsActivePort file not found` failure occurs before attachment, authentication checks or Rovo submission. The bundled Playwright discovery reads the default Chrome data location for the CLI's OS/user. Its multiline setup hint was lost when the adapter kept only the first error line. The adapter now returns a stable error code and explicit setup steps while suppressing the profile path; the README, skill and single setup prompt describe Chrome's supported enable/approve flow and environment limitations.

Two offline regression cases inject this failure at the Playwright connection boundary for status and ask. They verify actionable diagnostics, no submission, no request record and lock release. These tests validate error handling, not any browser's settings.

## MCP fallback development checks

Version 0.1.0a2 adds the skill fallback, packaged reference and local handoff guard. Offline tests cover reservation persistence, cross-session/cross-transport blocking, prompt/account/site/request correlation, stale/incomplete response rejection, output caps, dry-run behavior and installed begin/finish commands. These are local protocol tests with synthetic observations, not proof that a real Copilot MCP session can reach Rovo. No live Rovo prompts were submitted for this change.

The full suite passed 38 tests after installing 0.1.0a2, with the installed-command test process launched outside the checkout. Source/packaged skill parity and reference resolution passed. The generic Codex skill validator rejects the existing `disable-model-invocation` field; it was retained because [VS Code explicitly supports it](https://code.visualstudio.com/docs/agent-customization/agent-skills) for slash-only invocation. A separate YAML check validated the Copilot frontmatter and local reference paths; this does not prove live Copilot discovery.

An independent source-level behavioral review covered seven scenarios: eligible fallback, existing draft, direct ask timeout, new-profile requirement, lost MCP click result, an unresolved direct request under another session, and stale completion evidence. It found no routing blocker and confirmed stop/no-resend behavior for the unsafe cases. This was reasoned review, not a live MCP tool execution.
