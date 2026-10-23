# Connection and setup troubleshooting

Read when a result has `next: stop` for a connection, setup or layout error, or when preparing Chrome. SKILL.md's authority limits still apply. `doctor` reports the installed runtime; do not claim authentication from it.

## Chrome attachment

The direct route's supported prerequisite is Chrome 144+ with explicit enablement at `chrome://inspect/#remote-debugging` in the same OS/user environment as the CLI; the user approves the browser prompt. Do not fabricate DevToolsActivePort or add launch flags as a workaround. Multiple Chrome contexts are rejected because the approved profile is ambiguous.

If remote debugging is enabled but file discovery fails, use global `--chrome-port PORT` before `session` only when Chrome's debugging UI advertises that port or local process ownership proves it belongs to the intended normal Chrome. The connector uses a fixed loopback WebSocket, preserves Chrome approval and freezes the port for the connection. Do not guess ports, change profiles, fabricate discovery files or automatically switch endpoints after a failed attachment. Missing discovery is not proof debugging is disabled. One-shot commands accept the same global option.

`chrome_connection_failed` includes measured attachment time and sanitized guidance. Pending approval is only a possible cause; a generic failure does not automatically expand MCP eligibility. Failed startup exits immediately. An established connection lost with `chrome_connection_lost` ends the session without reconnecting. Do not relaunch an ask after a missing or uncertain result.

For a user-confirmed managed Chrome connection block, the MCP fallback is allowed only after this invocation's status failed before submission with `not_attempted` and `retry_safe: true`. Configuration checks must establish the MCP route is independently permitted; never infer this just from tool presence.

## Owned tab

The direct CLI creates one tab in the existing approved Chrome context at the requested site's `/jira/for-you`; no Jira tab or pre-opened Rovo panel is required. It checks the account, opens Ask Rovo once if absent, and waits up to 10 seconds for the panel/composer after navigation (separately bounded to 10 seconds). Keep all existing user tabs and drafts intact. The same connection reuses its bound tab even when other Rovo panels open. If its tab closes, replacement is allowed only after the unresolved-delivery guard passes; a tab navigated outside Jira is rejected without refresh. Never manually refresh, close user panels or switch targets to evade a guard. Inspect `readiness_phase` on preparation failure. There is no automatic reload or submission retry.

At exit the CLI closes only its own verified empty idle legacy tab after status; conversation content, drafts, uncertain delivery, failed preparation and unverified layouts retain the tab with a stderr notice. There is no daemon, automatic reconnect or approval bypass.

## Mini-modal layout

`readiness: authenticated_ui_read_only` or `error_code: rovo_layout_unverified` stops before ask, list or export. Mini-modal status confirms only the account, panel and visible composer; `active_generation: null` means unknown, even with `retry_safe: true`. Its `Message sent.` label does not prove completion. Do not send or switch transports to bypass this limit. Missing generation/attachment-state and completion-transition evidence must come from read-only observation, without conversation/account text or a new diagnostic question.

## Limits

Automatic conversation binding is direct CLI only; MCP keeps its separate guarded workflow, is agent-mediated, may use more Copilot context, and has offline guard tests but no live acceptance yet. Local guards cannot stop unrelated tools or a person controlling the browser. Direct text, one PNG, source toggles and chat continuity passed on macOS; grounded GitHub retrieval and Copilot acceptance remain open.
