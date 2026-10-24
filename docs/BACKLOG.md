# Backlog

Remaining work for `main` (package `0.1.0a6`). Details and evidence live in [Validation](VALIDATION.md) and [Connection improvements](CONNECTION_IMPROVEMENTS.md).

## Copilot checks

Open: whether Copilot keeps one session process alive between commands (see [Connection improvements](CONNECTION_IMPROVEMENTS.md)).

## Speed work (architecture review, candidate 1 shipped in `cab2512`)

macOS, one retained session, in seconds. "Before" is the baseline after candidate 1. "Now" is one live run each on 2026-10-24 after items 5, 6 and 8, not an average:

| Phase | New chat, before | New chat, now | Follow-up, before | Follow-up in open chat, now | Follow-up via picker, now |
|---|---:|---:|---:|---:|---:|
| `generate` (Rovo writing plus completion wait) | 7.5 | 7.4 | 6.7 | 7.2 | 6.9 |
| `select` (pick or confirm the chat) | 0.8 | 0.06 | 1.1 | 0.03 | 1.4 |
| `capture` (read back and bind the chat) | 1.1 | 0.02 | 0.0 | 0.01 | 0.01 |
| `attach` + `prepare` | 0.04 | 0.02 | 0.01 | 0.20 | 0.03 |
| Total | 9.5 | 7.5 | 7.8 | 7.5 | 8.4 |

`generate` is almost all Rovo and varies run to run. A follow-up uses the open chat while the session stays alive; the picker runs only after a restart or when the open chat cannot be proven, and that path was not sped up.

5. **Single snapshot per completion check.** Shipped. It reads each check at one consistent moment; it was never a speed fix. Each old read cost about 1 to 3 ms, so it could save at most about 20 ms. Our code adds only about 0.15 to 0.45 s to `generate` (completion is accepted on the first passing 200 ms check, with no settle window); the rest is Rovo. The live before/after (new chat 6.7 s then 8.5 s, follow-up 6.5 s then 6.8 s, one sample each) is Rovo's own variance. The in-page completion wait has since shipped: the page itself returns as soon as a turn completes (median 1.6 ms after completion in headless Chrome, versus 0 to 200 ms with the old poll), and one live ask completed with verified continuity. See [the measured results](VALIDATION.md#verified-in-page-completion-wait-2026-10-24). The repeated idle and signature reads are also gone: a follow-up makes about 9 fewer browser round trips before sending (about 1 to 3 ms each), an explicit `--chat` or verified-empty new chat 6 fewer, and a clicked New chat is unchanged. No cuts remain on this item.
6. **Warm-tab fast path.** Shipped and live-verified for consecutive follow-ups in one retained connection. Covered by the source and installed-wheel suites (302 passed, 8 opt-in browser checks skipped in each). A direct follow-up in the same retained connection skips the picker only when the same owned page, request, non-zero turn count, turn signature and last message ID still match, the picker is closed and the panel was not reopened. Show more may open during narrow-window preparation; the chat checks run afterward. An intervening operation, error, changed evidence or restart uses the normal picker path. Existing account, draft and uncertain-delivery guards still apply. One live comparison reduced selection from 1,240 ms through the picker to 33 ms through the shortcut, saving 1,207 ms (97.3%). The message ID recorded after completion still matched at the next follow-up. Total time fell from 9,068 ms to 7,468 ms, but 421 ms of that difference came from Rovo generation and cannot be attributed to the shortcut. This is one comparison, not an average; longer-term message-ID stability, other layouts and behavior under Copilot remain unverified. A changed or missing ID disables the shortcut. See [the measured results](VALIDATION.md#verified-follow-up-speed-2026-10-24).
7. **Re-adopt the owned tab across restarts.** Only if gate 2 shows the host cannot keep one process alive.
8. **New-chat capture from the send request.** Shipped and live-verified. A new chat's ID is read from the single Rovo send request (`POST .../chat/conversation/{id}/message/stream/sse`) the owned tab makes after Submit, so neither chat-list visit remains. The completed turn in that tab must still match; a missing, duplicate or malformed send leaves `continuity_status: unavailable` with the answer kept. If a bound ID were ever wrong, the next follow-up's saved-history check stops before sending. One live ask: select fell from 719 to 763 ms to 55 ms and capture from 1,155 ms to 14 ms, about 1.85 s per new chat. A read-only export of the bound ID showed exactly that turn. See [the measured results](VALIDATION.md#verified-new-chat-capture-2026-10-24).
9. **Older history paging.** Shipped. `chat list`, `chat export` and the picker scroll Rovo's lazy history until Rovo reports the end, and report `coverage: "complete"` only then. Live: all 29 chats listed (25 were rendered before), and the oldest exported through the picker. See [Validation](VALIDATION.md#verified-history-paging-2026-10-24).

## Unverified or not implemented

- Long-term stability of the send-request URL used for new-chat capture. A change disables capture safely (`continuity_status: unavailable`), not delivery.
- Cause of the original post-readiness pre-submit click timeout (not reproduced). Likely the same hidden-tab pause behind the `Show more` timeouts, fixed by the CLI's own window (see [Validation](VALIDATION.md#verified-hidden-cli-window-2026-10-24)); a recurrence now reports `page_hidden` or `input_not_acknowledged`.
- Mini-modal ask, list and export (blocked by `rovo_layout_unverified`).
- Grounded GitHub retrieval and structured citations.
- MCP fallback in a real Copilot session.
- Loading older turns of a chat longer than one Rovo page (no such chat on the development site), and lists past Rovo's first 100 chats.
- `chat list` and `chat export` retain their tab (picker or exported chat left open), so each leaves an off-screen window.
- More than two images, upload error variants, uncertain-delivery reconciliation, other operating systems, headless operation.
- Token and billing savings measured in Copilot (current figures are byte estimates).
