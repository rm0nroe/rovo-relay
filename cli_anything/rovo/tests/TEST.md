# Test plan and evidence boundary

For the repeatable development-Mac workflow, normal-Chrome checks, evidence and cleanup, see [the testing runbook](../../../docs/TESTING_RUNBOOK.md).

Run the installed-command suite with `CLI_ANYTHING_FORCE_INSTALLED=1`. The offline suite must not contact Rovo, create browser sessions or spend provider credits. Argument fixtures use example domains and a synthetic conversation UUID.

Unit checks cover URL/account/session validation, site locking, durable uncertain-delivery state, completion after a matching new turn, output bounds and PNG count/size/signature/name policy. Subprocess checks cover installed command resolution, packaged skill discovery, JSON errors, dry-run, image arguments, source choices and conversation IDs.

Persistent-session tests reuse synthetic Playwright boundaries to verify one attachment across commands, bound-tab/account/composer/delivery checks, lock release while idle, no reconnect after failure, startup flushing and JSON framing, immutable binding, malformed input and stdin-prompt rejection, recoverable preparation errors, terminal uncertain sends/timeouts, EOF/signals and cleanup failures. Human REPL reuse is exercised without a terminal or browser. Installed subprocess checks also cover session help, doctor capability discovery and dry-run startup. Connection diagnostics additionally prove that a flushed stderr notice precedes a new attachment and is not repeated on reuse, and that sanitized failure metadata distinguishes runtime startup from browser attachment without changing delivery or retry semantics. No real browser or live Rovo questions are needed.

Explicit Chrome port cases verify range validation before attachment, fixed loopback WebSocket construction, connection reuse, one-shot/REPL routing, immutable port selection, dry-run without attachment and no automatic endpoint fallback. Live acceptance is separately documented in `docs/VALIDATION.md`; the offline suite does not use a live debugging port.

The recorded development live results and remaining gates are summarized in `docs/VALIDATION.md` at the repository root. Raw logs and personal identifiers are intentionally not included. Runtime changes require installed-candidate checks with the executable directory on PATH; documentation-only changes outside the package use document checks and do not repeat live tests.

Tab/readiness regressions cover a connection-owned normal-Chrome tab with zero or multiple existing Jira/Rovo tabs, one tab reused across commands, closed-tab replacement, ambiguous contexts, delayed account/panel/composer controls, bounded launcher clicks and navigation timeout recovery without another navigation. Account mismatch and leaving Jira stop preparation. Cleanup closes only verified empty owned legacy tabs and preserves drafts, attachments, active responses, content, mini-modals and uncertain submissions. Existing user tabs are never inspected or mutated by selection; unresolved delivery blocks before tab creation. No test reloads or retries a send.

Overflow regressions keep Show more open between account verification and the Ask Rovo click, including an already-open panel and refusal for the wrong account. Click-diagnostic cases verify fixed control labels, allowlisted blockers, private-data suppression, no retry, uncertain-submit guards and preservation of completed answers when capture fails.

The completion snapshot (`observe_turn`) has an opt-in equivalence check, `ROVO_DOM_CHECK=1`, which compares its single page read with the former per-field locator reads on synthetic HTML in a throwaway headless Chrome. It is skipped by default because it starts a browser; it never opens Rovo or the user's Chrome.

Continuity tests cover automatic binding and reopening across processes, explicit new chats, matching loaded history, missing or ambiguous conversation IDs and refusal on changed history. `next_action` tests distinguish safe input correction from browser failures that require stopping. The installed suite at `7de0fbc` passed 249 tests; counts are candidate-specific, not permanent expectations.
