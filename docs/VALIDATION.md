# Validation status

## Local checks

The development baseline passed 20 unit and installed-command tests. They cover destination and identity validation, site locks, durable uncertain delivery, stale response rejection, output bounds, image policy, installed skill discovery, dry-run behavior and command validation. The clean repository passed all 20 tests after a fresh installation on 2026-10-21, with `CLI_ANYTHING_FORCE_INSTALLED=1` and the test process launched outside the checkout. The wheel built successfully and its package files matched the sanitized source. No browser request is made by this suite.

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

Grounded GitHub retrieval, new-chat ID capture, structured citations, multiple-image live tests, upload error variants, older history pagination, uncertain-delivery reconciliation, actual Copilot invocation, other operating systems, headless operation and measured token savings remain unverified or unimplemented.

Live calls consume Rovo credits. The development allowance was exhausted; no further Rovo prompts are part of the repository preparation. A finished CLI response is not a passing code-retrieval result.

## Chrome connection diagnostic regression

The reported `DevToolsActivePort file not found` failure occurs before attachment, authentication checks or Rovo submission. The bundled Playwright discovery reads the default Chrome data location for the CLI's OS/user. Its multiline setup hint was lost when the adapter kept only the first error line. The adapter now returns a stable error code and explicit setup steps while suppressing the profile path; the README, skill and single setup prompt describe Chrome's supported enable/approve flow and environment limitations.

Two offline regression cases inject this failure at the Playwright connection boundary for status and ask. They verify actionable diagnostics, no submission, no request record and lock release. These tests validate error handling, not any browser's settings.

## MCP fallback development checks

Version 0.1.0a2 adds the skill fallback, packaged reference and local handoff guard. Offline tests cover reservation persistence, cross-session/cross-transport blocking, prompt/account/site/request correlation, stale/incomplete response rejection, output caps, dry-run behavior and installed begin/finish commands. These are local protocol tests with synthetic observations, not proof that a real Copilot MCP session can reach Rovo. No live Rovo prompts were submitted for this change.

The full suite passed 38 tests after installing 0.1.0a2, with the installed-command test process launched outside the checkout. Source/packaged skill parity and reference resolution passed. The generic Codex skill validator rejects the existing `disable-model-invocation` field; it was retained because [VS Code explicitly supports it](https://code.visualstudio.com/docs/agent-customization/agent-skills) for slash-only invocation. A separate YAML check validated the Copilot frontmatter and local reference paths; this does not prove live Copilot discovery.

An independent source-level behavioral review covered seven scenarios: eligible fallback, existing draft, direct ask timeout, new-profile requirement, lost MCP click result, an unresolved direct request under another session, and stale completion evidence. It found no routing blocker and confirmed stop/no-resend behavior for the unsafe cases. This was reasoned review, not a live MCP tool execution.
