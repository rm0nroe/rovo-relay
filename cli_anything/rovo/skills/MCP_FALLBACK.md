# Existing Playwright MCP fallback

Read only when SKILL.md's pre-submission fallback conditions hold. This is a skill workflow using the agent's tools, not a new server or a CLI connection to MCP. The local `mcp begin/finish` commands only guard delivery and validate agent-observed completion.

## Check the existing connection

Inspect available tool schemas and permitted configuration; do not expose tokens. Tool names vary by installation. Typical tools include `browser_tabs`, `browser_snapshot`, `browser_evaluate`, `browser_click`, `browser_type`, `browser_file_upload` and `browser_wait_for`. Use actual discovered tools, not guessed names or parameters. Do not require `browser_run_code`.

Use only the existing allowed connection. If a call would need a new browser/profile, extension, permission or configuration change, stop and report that requirement. Listing tabs can start a browser in some configurations: check connection mode first. If the tool cannot establish this, do not assume it is the user's Chrome.

List existing tabs whose origin equals SITE and path starts `/jira/` or `/browse/`. Inspect panel visibility on those tabs and select the only one with a visible Rovo panel, regardless of which Chrome tab is foreground. Stop if no eligible tab exists, no panel is visible, or multiple panels are visible; ask the user to leave Rovo open only in the intended tab while preserving drafts. On the selected tab, confirm the expected account; decline a different account, an unknown identity or an unrelated browser. Keep that tab for the operation; recheck its origin and allowed path before submission and during response monitoring, and never switch tabs after an error or navigation. Never use cookies as identity evidence. Do not submit a question just to test access.

An empty composer or disabled New chat button does not prove that a UI variant is safe. Verify its generation, attachment and completion controls before any chat action; do not use MCP to bypass direct `authenticated_ui_read_only` readiness or a `rovo_layout_unverified` result. Mini-modal status leaves generation unknown; its `Message sent.` label is not completion evidence.

Read-only user requests (status, loaded chat listing/export) need no send reservation, but must still obey identity, draft and uncertainty safeguards. Report MCP inspection as such, not as a successful CLI status.

## Prepare the authorized question

1. Keep the same SITE, SESSION and EMAIL. Validate the prompt and any image files using the CLI's `--dry-run ask` with all requested flags; do not contact the direct browser again. Never silently drop requested images, source selection or chat continuity if MCP lacks the required capability. Inputs must be accessible to the MCP host; do not copy confidential files to a new host without authorization.
2. Inspect the Rovo composer. Stop on any existing draft, attachment or active generation. Start New chat, or reopen only an observed UUID requested by the user. Recheck the destination, account and idle composer after selecting the chat. Do not clear a draft to proceed.
3. Apply the requested GitHub chat source filter and verify its visible selected state. Upload only the authorized PNGs through the existing MCP file-upload tool and verify each attachment is ready. Do not modify connector installation or repo permissions. Fill the prompt with submit disabled, verify exact text and the enabled Submit button.
4. Capture the response-card count **after** selecting the new/existing chat and **before** submitting. Use current DOM observations, not invented numbers. Immediately before the one Submit click, run:

```sh
rovo-relay --json --site SITE --session SESSION --account EMAIL mcp begin --prompt-file PRIVATE_PROMPT_FILE --before-count N
```

Continue only after exit 0 with `execution_status: reserved` and a request ID. Recheck the exact site, account and filled prompt immediately before Submit and stop if anything changed; retain the reservation on uncertainty. This deliberately records `attempted_unknown` before the click. If the command fails, its output is missing, or the context is interrupted, do not submit. Do not call begin again to manufacture a new request. The reservation blocks another send through either mode, even under another session name.

## Submit once and observe

Use exactly one MCP Submit click (never Enter plus click). Once it is attempted, a tool error or lost response is uncertain delivery. Do not repeat it or switch to the CLI. Keep the reservation if anything is uncertain, including an interruption between reservation and click.

Observe a new turn belonging to the exact prompt: generation must have started (`Rovo is thinking` or visible Stop generating), response count must exceed the saved baseline, latest user text must match, status must become `Response complete.`, Stop generating must be absent, and answer must be nonempty. A preexisting completion label or a quiet interval is insufficient. If the UI variant lacks reliable evidence, leave it blocked and report the limitation.

Use bounded waits, up to 180 seconds by default. Repeated read-only observation is allowed; repeated submission is not. Keep intermediate snapshots compact. Never infer completion from elapsed time. Preserve user tabs; do not close the shared MCP browser.

Use only observed fields to write a private UTF-8 JSON evidence file. It must contain these keys (values below describe the required types, not literal evidence):

| Key | Observed value |
|---|---|
| request_id | ID from successful begin |
| site, account | Exact current origin and verified account |
| started | Boolean: generation was observed for this turn |
| count | Integer: current response-card count |
| status | Exact current completion status text |
| generating | Boolean: Stop generating is currently visible |
| user_text | Exact latest user message text |
| answer | Assistant answer text, without button labels |

Then run:

```sh
rovo-relay --json --site SITE --session SESSION --account EMAIL mcp finish --evidence-file PRIVATE_EVIDENCE_FILE
```

Do not fill missing fields with desired values to pass validation. Only a successful finish clears the pending handoff. It validates correlation and types, caps the returned answer at 12,000 characters, and marks `completion_evidence: agent_observed` and `retrieval_assessment: unverified`. It cannot independently prove what the MCP browser displayed or verify code facts. Never edit local records manually to unblock a failed finish.

Return the bounded answer with `transport: playwright_mcp`, truncation and retrieval caveats. Keep evidence private and outside Git. On failure, report the request ID and submission state without submitting again. Manual reconciliation of uncertain requests is not implemented.
