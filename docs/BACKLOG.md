# Backlog

What remains, as of 2026-10-23 on `main` (package `0.1.0a6`). Details and evidence live in [Validation](VALIDATION.md) and [Connection improvements](CONNECTION_IMPROVEMENTS.md).

## Copilot checks

Open: whether Copilot keeps one session process alive between commands (see [Connection improvements](CONNECTION_IMPROVEMENTS.md)).

## Speed work (architecture review, candidate 1 shipped in `5299567`)

Measured baseline after candidate 1, one retained session on macOS, in seconds:

| Phase | New chat | Follow-up |
|---|---|---|
| `generate` (Rovo writing plus completion wait) | 7.5 | 6.7 |
| `select` (open the chat picker, pick the chat) | 0.8 | 1.1 |
| `capture` (read back and bind the new chat) | 1.1 | 0.0 |
| `attach` + `prepare` | 0.04 | 0.01 |
| Total | 9.5 | 7.8 |

5. **Single snapshot per completion check.** Replace about six browser reads per 200 ms tick with one. Its gain sits inside `generate`; compare the same question before and after.
6. **Warm-tab fast path.** Skip the picker on an untouched owned tab (targets `select`). Decide first whether same tab, same last-turn hash and no navigation is enough identity evidence.
7. **Re-adopt the owned tab across restarts.** Only if gate 2 shows the host cannot keep one process alive.

## Unverified or not implemented

- Cause of the original post-readiness pre-submit click timeout (diagnostics shipped in `c9f380a`; not reproduced).
- Mini-modal ask, list and export (blocked by `rovo_layout_unverified`).
- Grounded GitHub retrieval and structured citations.
- MCP fallback in a real Copilot session.
- Multiple images, upload error variants, older history pagination, uncertain-delivery reconciliation, other operating systems, headless operation.
- Token and billing savings measured in Copilot (current figures are byte estimates).
