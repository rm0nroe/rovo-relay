# Backlog

Remaining work for `main` (package `0.1.0a6`). Details and evidence live in [Validation](VALIDATION.md) and [Connection improvements](CONNECTION_IMPROVEMENTS.md).

## Owner checks

Owner-run Copilot host checks are tracked outside this repository. Check 2 asks whether the host keeps one session process alive.

## Speed work (architecture review, candidate 1 shipped in `cab2512`)

Measured baseline after candidate 1, one retained session on the development Mac, in seconds:

| Phase | New chat | Follow-up |
|---|---|---|
| `generate` (Rovo writing plus completion wait) | 7.5 | 6.7 |
| `select` (open the chat picker, pick the chat) | 0.8 | 1.1 |
| `capture` (read back and bind the new chat) | 1.1 | 0.0 |
| `attach` + `prepare` | 0.04 | 0.01 |
| Total | 9.5 | 7.8 |

5. **Single snapshot per completion check.** Shipped. It reads each check at one consistent moment; it was never a speed fix. Each old read cost about 1 to 3 ms, so it could save at most about 20 ms. Our code adds only about 0.15 to 0.45 s to `generate` (completion is accepted on the first passing 200 ms check, with no settle window); the rest is Rovo. The live before/after (new chat 6.7 s then 8.5 s, follow-up 6.5 s then 6.8 s, one sample each) is Rovo's own variance. Remaining cuts, largest first: wait for completion inside the page instead of polling (about 100 ms), and merge repeated idle and signature reads (about 30 ms).
6. **Warm-tab fast path.** Shipped and live-verified for consecutive follow-ups in one retained connection. Covered by the source and installed-wheel suites (302 passed, 8 opt-in browser checks skipped in each). A direct follow-up in the same retained connection skips the picker only when the same owned page, request, non-zero turn count, turn signature and last message ID still match, the picker is closed and the panel was not reopened. Show more may open during narrow-window preparation; the chat checks run afterward. An intervening operation, error, changed evidence or restart uses the normal picker path. Existing account, draft and uncertain-delivery guards still apply. One live comparison reduced selection from 1,240 ms through the picker to 33 ms through the shortcut, saving 1,207 ms (97.3%). The message ID recorded after completion still matched at the next follow-up. Total time fell from 9,068 ms to 7,468 ms, but 421 ms of that difference came from Rovo generation and cannot be attributed to the shortcut. This is one comparison, not an average; longer-term message-ID stability, other layouts and Copilot-host behavior remain unverified. A changed or missing ID disables the shortcut. See [the measured results](VALIDATION.md#verified-follow-up-speed-2026-10-24).
7. **Re-adopt the owned tab across restarts.** Only if gate 2 shows the host cannot keep one process alive.
8. **New-chat capture from the send request.** Shipped and live-verified. A new chat's ID is read from the single Rovo send request (`POST .../chat/conversation/{id}/message/stream/sse`) the owned tab makes after Submit, so neither chat-list visit remains. The completed turn in that tab must still match; a missing, duplicate or malformed send leaves `continuity_status: unavailable` with the answer kept. If a bound ID were ever wrong, the next follow-up's saved-history check stops before sending. One live ask: select fell from 719 to 763 ms to 55 ms and capture from 1,155 ms to 14 ms, about 1.85 s per new chat. A read-only export of the bound ID showed exactly that turn. See [the measured results](VALIDATION.md#verified-new-chat-capture-2026-10-24).

## Unverified or not implemented

- Recurrence of `Click timed out: Show more` at startup: seen again once on 2026-10-24 during a status-only run on the narrow window, before any submission. Not reproduced since.
- Long-term stability of the send-request URL used for new-chat capture. A change disables capture safely (`continuity_status: unavailable`), not delivery.
- Cause of the original post-readiness pre-submit click timeout (diagnostics shipped in `7c5f895`; not reproduced). Clicks whose input the page never acknowledges now report `input_not_acknowledged`, which narrows the next occurrence.
- Mini-modal ask, list and export (blocked by `rovo_layout_unverified`).
- Grounded GitHub retrieval and structured citations.
- MCP fallback in a real Copilot session.
- Multiple images, upload error variants, older history pagination, uncertain-delivery reconciliation, other machines and OS versions, headless operation.
- Token and billing savings measured in Copilot (current figures are byte estimates).
