# Backlog

What remains, as of 2026-10-23 on `main` (package `0.1.0a6`). Details and evidence live in [Validation](VALIDATION.md) and [Connection improvements](CONNECTION_IMPROVEMENTS.md).

## Blocked on the Copilot host

1. **Install and accept on the Copilot host.** Update to current `main`, then run the two-question continuity check from the [setup prompt](COPILOT_SETUP_PROMPT.md).
2. **Session-lifetime gate.** Does Copilot keep one `session` process and its streams alive across separate skill invocations? Two `status` checks, one process, no Rovo question. See [Next gate](CONNECTION_IMPROVEMENTS.md#next-gate-reuse-across-skill-invocations).
3. **Shorter host timeout.** Compare one failed and one successful trace from the same revision before changing any budget. See [Diagnose the shorter timeout](CONNECTION_IMPROVEMENTS.md#diagnose-the-shorter-timeout-before-changing-it).

## Needs an access check (Atlassian admin or OAuth)

4. **Official code access.** Check Code context eligibility, then discover MCP v2 `getCodeFile` and `searchCode` and fetch one known file. If it passes, code retrieval uses the official interface. See [First gate](CONNECTION_IMPROVEMENTS.md#first-gate-official-access).

## Speed work (architecture review, candidate 1 shipped in `5299567`)

Measured baseline after candidate 1, one retained session on the development Mac, in seconds:

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
- Multiple images, upload error variants, older history pagination, uncertain-delivery reconciliation, other machines and OS versions, headless operation.
- Token and billing savings measured in Copilot (current figures are byte estimates).
