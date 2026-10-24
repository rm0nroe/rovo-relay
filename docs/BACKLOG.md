# Backlog

What remains, as of 2026-10-23 on `main` (package `0.1.0a6`). Details and evidence live in [Validation](VALIDATION.md) and [Connection improvements](CONNECTION_IMPROVEMENTS.md).

## Owner checks

Owner-run Copilot host checks are tracked outside this repository. Check 2 asks whether the host keeps one session process alive.

## Speed work (architecture review, candidate 1 shipped in `5299567`)

Measured baseline after candidate 1, one retained session on the development Mac, in seconds:

| Phase | New chat | Follow-up |
|---|---|---|
| `generate` (Rovo writing plus completion wait) | 7.5 | 6.7 |
| `select` (open the chat picker, pick the chat) | 0.8 | 1.1 |
| `capture` (read back and bind the new chat) | 1.1 | 0.0 |
| `attach` + `prepare` | 0.04 | 0.01 |
| Total | 9.5 | 7.8 |

5. **Single snapshot per completion check.** Shipped. It reads each check at one consistent moment; it was never a speed fix. Each old read cost about 1 to 3 ms, so it could save at most about 20 ms. Our code adds only about 0.15 to 0.45 s to `generate` (completion is accepted on the first passing 200 ms check, with no settle window); the rest is Rovo. The live before/after (new chat 6.7 s then 8.5 s, follow-up 6.5 s then 6.8 s, one sample each) is Rovo's own variance. Remaining cuts, largest first: capture a new chat's ID without opening the chat list twice (0.6 to 2 s, unmeasured; needs a provable single-ID source), wait for completion inside the page instead of polling (about 100 ms), and merge repeated idle and signature reads (about 30 ms).
6. **Warm-tab fast path.** Skip the picker on an untouched owned tab (targets `select`, 0.8 to 1.1 s per follow-up). Same tab, same last-turn hash and same URL is not enough: the URL never carries the chat ID, and a different chat with an identical last turn would pass. Safe version: an in-memory marker set only after a verified ask and cleared on any error or other action, the same page and `request_id`, no panel reopen or overflow click during preparation, picker closed and idle, and an equal non-zero turn count and `turn_signature`; anything else falls back to the picker. First probe read-only whether the open panel exposes the conversation ID, which would close the identical-turn gap.
7. **Re-adopt the owned tab across restarts.** Only if gate 2 shows the host cannot keep one process alive.

## Unverified or not implemented

- Cause of the original post-readiness pre-submit click timeout (diagnostics shipped in `c9f380a`; not reproduced). Clicks whose input the page never acknowledges now report `input_not_acknowledged`, which narrows the next occurrence.
- Mini-modal ask, list and export (blocked by `rovo_layout_unverified`).
- Grounded GitHub retrieval and structured citations.
- MCP fallback in a real Copilot session.
- Multiple images, upload error variants, older history pagination, uncertain-delivery reconciliation, other machines and OS versions, headless operation.
- Token and billing savings measured in Copilot (current figures are byte estimates).
