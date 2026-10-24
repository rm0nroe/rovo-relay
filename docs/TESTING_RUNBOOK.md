# Development testing runbook

Use this runbook when changing Rovo Relay on the development Mac and validating it in the owner's existing normal Chrome and approved Atlassian account. Start offline, verify the installed artifact, then exercise only the browser behavior affected by the change. Keep one connection alive and collect evidence as you go. Do not repeat a successful live question to improve a report.

This document describes the method; [VALIDATION.md](VALIDATION.md) records results and [COPILOT_SETUP_PROMPT.md](COPILOT_SETUP_PROMPT.md) remains the single canonical Copilot-host handoff. Local success does not establish organizational approval, Copilot-host compatibility or grounded retrieval. Examples deliberately omit the actual account, tenant, local paths and conversation IDs.

## 1. Choose the smallest test that proves the change

| Change | Offline coverage | Browser acceptance | Live questions |
|---|---|---|---|
| Documentation only | Links, examples, mirrors and privacy review | None unless the instructions themselves need a new observation | 0 |
| Tab selection, connection or page readiness | `test_browser_tabs.py`, `test_session.py` | Startup plus another status; affected tab/panel cases | 0 |
| Automatic conversation continuity | `test_continuity.py`, `test_session.py` | Initial answer plus distinct follow-up, same observed chat and added visible turn | 2 from scratch; 1 additional when a verified synthetic first turn already exists |
| Existing conversation to a new chat | Existing continuity/browser tests | Open the verified synthetic chat read-only; `ask --new`; compare distinct IDs and export both chats | 1 additional; original must remain unchanged |
| Continuity after process restart | Existing continuity/session tests | After a verified first turn, detach normally; a fresh process reopens the same chat for a distinct follow-up | 1 additional to a verified first turn; 2 total from scratch |
| PNG handling or source selection | Argument/state tests and affected browser fixtures | One authorized synthetic image or source-specific request | Agree the minimum budget first |
| GitHub file retrieval | Existing guards and command parsing | A known file that manual Rovo access already retrieves; compare returned contents/source evidence | Separate authorized retrieval test |

Live-question counts are budgets, not standing permission. Use the user's authorized scope and available allowance. A request to check readiness does not authorize a Rovo question. Do not enable paid overage. A model's promise to be read-only cannot enforce provider permissions.

Before edits, trace the shared handler and every affected caller: one-shot CLI, foreground `session`, REPL, explicit `--chat`, list/export, fixtures, packaged docs and skill. Add a focused regression for meaningful logic; use synthetic Playwright doubles for wrong accounts, drafts, missing IDs, timeouts and disconnects. Do not spend credits or disturb real user conversations to manufacture negative cases.

## 2. Capture the baseline and keep evidence outside Git

Read applicable `AGENTS.md` instructions. Preserve unrelated changes and never reset or stash them to simplify testing. Check the current checkout, branch, merge state and installed executable. Resolve the shared graph if present before code exploration; otherwise read the affected source directly.

Example setup for the existing macOS checkout, using its existing `.venv`:

```sh
export ROVO_REPO="$(git rev-parse --show-toplevel)"
umask 077
mkdir -p "$HOME/.local/state/rovo-relay/tests"
export ROVO_EVIDENCE="$(mktemp -d "$HOME/.local/state/rovo-relay/tests/run.XXXXXX")"
git status -sb > "$ROVO_EVIDENCE/git-before.txt"
git rev-parse HEAD > "$ROVO_EVIDENCE/base-commit.txt"
"$ROVO_REPO/.venv/bin/python" --version > "$ROVO_EVIDENCE/python.txt"
```

Record dirty-file names, the candidate diff or file hashes, OS, Chrome version/channel, CLI environment, caller deadline and authorized live-question budget. A base commit does not identify uncommitted candidate code. If the current venv or tools are unavailable, report that gap before installing replacements.

Keep private artifacts together: test logs, wheel, package-parity output, startup/command JSON, sanitized stderr, screenshots and a brief verdict. Raw output can include tenant/account identity, local paths, conversation IDs and private content. Never commit these, even if an ignore rule happens to cover them. Use only synthetic identities in repository fixtures.

## 3. Run offline checks, then verify what is actually installed

Run the focused regression during implementation. Once the change is ready, run the full relevant suite. Reuse installed dependencies; no Playwright browser download is needed.

```sh
cd "$ROVO_REPO"
.venv/bin/python -m pytest cli_anything/rovo/tests -q --tb=short
git diff --check
```

These tests must not attach to Chrome or contact Rovo. The synthetic browser fixture is in `test_browser_tabs.py`; session lifecycle tests reuse it. `test_full_e2e.py` tests installed command execution, not live provider behavior. Do not describe it as a live end-to-end test.

### Build once per candidate

A version string is insufficient: the current release and multiple fixes report `0.1.0a6`. Record source revision/diff and compare installed bytes. Prefer a wheel and a non-editable installation so the installed test cannot silently use the checkout.

The normal isolated build uses the requirements declared in `pyproject.toml` (`setuptools==84.2.1`, `wheel==0.48.0`) and succeeded for the current development fix. It may resolve build dependencies; `--no-deps` skips runtime dependency resolution, not build requirements:

```sh
cd "$ROVO_REPO"
.venv/bin/python -m pip wheel --no-deps --wheel-dir "$ROVO_EVIDENCE/wheel" .
```

When the existing venv already has usable build dependencies, this offline build uses them without fetching dependencies:

```sh
cd "$ROVO_REPO"
.venv/bin/python -m pip wheel --no-deps --no-build-isolation \
  --wheel-dir "$ROVO_EVIDENCE/wheel" .
```

Record the actual setuptools/wheel versions. This is not proof of the isolated pinned build unless those versions match `pyproject.toml`. Do not download a new backend merely to make a local check look green.

During an earlier October development run, pinned setuptools `84.2.1` was unavailable offline. The successful fallback used an already-cached setuptools `84.0.0` and installed wheel `0.48.0`. If an offline build is required and cannot import its backend, locate those existing tools and set `ROVO_SETUPTOOLS_DIR` and `ROVO_WHEEL_DIR` to their verified import roots. The historical fallback is:

```sh
cd "$ROVO_REPO"
PYTHONPATH="$ROVO_SETUPTOOLS_DIR:$ROVO_WHEEL_DIR" .venv/bin/python setup.py \
  egg_info --egg-base "$ROVO_EVIDENCE" \
  build --build-base "$ROVO_EVIDENCE/build" \
  bdist_wheel --bdist-dir "$ROVO_EVIDENCE/bdist" \
  --dist-dir "$ROVO_EVIDENCE/wheel"
```

Use this only when those packages already exist; record the deviation and retain the wheel. It is a local fallback, not a change to declared build requirements. Check each command's exit code before continuing. A missing backend is not a passing build.

Select the single wheel produced for this candidate, then install it without dependency resolution:

```sh
export ROVO_WHEEL="$(find "$ROVO_EVIDENCE/wheel" -maxdepth 1 -name '*.whl' -type f)"
test -f "$ROVO_WHEEL"
"$ROVO_REPO/.venv/bin/python" -m pip install --no-deps --force-reinstall "$ROVO_WHEEL"
```

If multiple wheel paths are returned, stop and select the exact candidate; do not install an arbitrary match.

### Test outside the checkout and compare package contents

Run this in a subshell so the working directory and environment changes do not leak into subsequent steps. `CLI_ANYTHING_FORCE_INSTALLED=1` makes a missing executable fail instead of falling back to module execution. Clearing `PYTHONPATH` prevents build-tool overrides from affecting validation.

```sh
(
  set -e
  cd "$ROVO_EVIDENCE" || exit 1
  unset PYTHONPATH
  export PATH="$ROVO_REPO/.venv/bin:$PATH"
  export CLI_ANYTHING_FORCE_INSTALLED=1
  "$ROVO_REPO/.venv/bin/python" -m pytest \
    "$ROVO_REPO/cli_anything/rovo/tests" -q --tb=short \
    > installed-tests.txt 2>&1
)
```

Read the log and exit status. Then verify both import location and contents, also outside the checkout:

```sh
(
  set -e
  cd "$ROVO_EVIDENCE" || exit 1
  unset PYTHONPATH
  "$ROVO_REPO/.venv/bin/python" - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import cli_anything.rovo

source = Path(os.environ['ROVO_REPO']) / 'cli_anything/rovo'
installed = Path(cli_anything.rovo.__file__).resolve().parent
assert installed != source.resolve(), 'Checkout is masking the installed package'
expected = {p.relative_to(source) for p in source.rglob('*.py')
            if 'tests' not in p.relative_to(source).parts}
expected |= {Path('README.md'), Path('utils/allow.sh')}
expected |= {p.relative_to(source) for p in (source / 'skills').glob('*.md')}
actual = {p.relative_to(installed) for p in installed.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts}
assert actual == expected, (actual - expected, expected - actual)
hashes = {}
for name in sorted(expected):
    data = (installed / name).read_bytes()
    assert data == (source / name).read_bytes(), str(name)
    hashes[str(name)] = hashlib.sha256(data).hexdigest()
Path('installed-parity.json').write_text(json.dumps(
    {'installed': str(installed), 'sha256': hashes}, indent=2))
print(f'{len(hashes)} installed files match source')
PY
  "$ROVO_REPO/.venv/bin/rovo-relay-cli" --json doctor
)
```

At `41ca8de`, the package contains 13 source/document files; the older continuity baseline had 12. Compare these four repository mirror pairs as well:

- `README.md` and `cli_anything/rovo/README.md`.
- `.github/skills/ask-rovo/SKILL.md` and `cli_anything/rovo/skills/SKILL.md`.
- `.github/skills/ask-rovo/MCP_FALLBACK.md` and `cli_anything/rovo/skills/MCP_FALLBACK.md`.
- `.github/skills/ask-rovo/TROUBLESHOOTING.md` and `cli_anything/rovo/skills/TROUBLESHOOTING.md`.

Once this candidate passes, stop repeating the same suite unless code changes, a failure, or an unresolved concern justifies another run. Rebuild/reinstall after runtime or packaged-file edits. Documentation-only edits outside the package do not require another live question.

## 4. Establish the normal-Chrome connection once

Use the owner's existing signed-in normal Google Chrome, in the same OS/user environment as the CLI. Confirm the intended Atlassian site and expected account privately from current setup; never infer a tenant from a nickname or substitute another account. Preserve existing tabs and drafts.

For agent-driven inspection, prefer native normal Chrome computer use (`cua.getApp("com.google.Chrome")` when available). Use the current session's assigned browser name for any named browser tooling, never a hardcoded or default session. The product test itself must run the installed CLI. A successful UI click through another tool does not prove that the CLI worked.

Chrome's supported remote-debugging setting and the owner's approval are prerequisites. Verify current Chrome/runtime compatibility against the canonical setup document. Do not fabricate `DevToolsActivePort`, copy profiles/cookies, or relaunch with debugging flags.

If discovery fails while the intended Chrome already exposes debugging, identify its advertised port or independently verify listener ownership. On this Mac, use `lsof -nP -iTCP:PORT -sTCP:LISTEN` with the observed port and check the owning process/profile. Only then use global `--chrome-port PORT`. The successful development path used Chrome's loopback browser WebSocket; a `/json/version` HTTP 404 did not diagnose that connection. Do not guess ports or automatically switch endpoints.

Set `ROVO_SITE`, `ROVO_ACCOUNT` and `ROVO_SESSION` privately. The site must be the intended HTTPS Atlassian origin, the account its expected email, and the session a stable task label using letters, digits, underscore or hyphen. A new session name does not bypass a site-wide unresolved-delivery record.

Start one retained foreground process with writable stdin and separately captured stdout/stderr:

```sh
"$ROVO_REPO/.venv/bin/rovo-relay-cli" \
  --site "$ROVO_SITE" --session "$ROVO_SESSION" --account "$ROVO_ACCOUNT" session
```

Add `--chrome-port "$ROVO_CHROME_PORT"` before `session` only when that port was verified. Do not use a one-command pipe that closes stdin before the next operation. Do not preload an ask. Read each flushed JSON result and follow its `next` action before the next command; missing `next` means stop. Startup includes capabilities, so a separate pre-ask `doctor` call is unnecessary. Send argument arrays with JSON serialization, not shell interpolation of prompt text. Use private prompt files: session stdin belongs to commands, so `--prompt-file -` is invalid.

The CDP attachment budget is 20 seconds; navigation and account/panel readiness have separate 10-second bounds. `ask --timeout` defaults to a 180-second response budget, not a whole-command deadline. Allow for preparation and post-response capture in the caller's deadline. If the caller terminates earlier, record its deadline and actual elapsed time; do not attribute that automatically to Chrome or extend deadlines without evidence.

## 5. Prove readiness without spending a question

Startup counts as the first status. Send `['status']` encoded as valid JSON:

```json
["status"]
```

For legacy send readiness, both results must have `exit_code: 0`, `readiness: authenticated_ui`, `tab_selection: connection_owned` and `readiness_phase: ready`. Also inspect `active_generation` and the idle composer before a send; status success alone does not make a draft or active generation safe. Verify one owned tab is reused and the retained process does not disconnect between commands. Do not infer connection reuse merely from two successful statuses; use process/connection observations or one bounded connection-diagnostic log when needed.

For tab/readiness changes, exercise only the relevant cases using agent-created test tabs:

| Case | Required observation |
|---|---|
| Several Jira/Rovo tabs already open | CLI prepares its own tab in its own off-screen window; user tabs remain unchanged and the user's active tab stays `visible` |
| Synthetic draft in a separate test tab | Draft survives status and owned-tab preparation |
| Owned panel closed | Next status opens it without refreshing the page |
| Narrow header with Show more | Account verification leaves overflow open through the Ask Rovo click; startup and another status succeed without resizing |
| Owned tab closed while session waits on stdin | Next status replaces it on the same connection after the delivery guard |
| EOF after status on an empty legacy panel | Client detaches and only its verified empty owned tab closes |

Live testing found queued Playwright close events could remain stale while stdin was idle. The fix drains pending events before checking the owned tab. Keep this regression offline and validate the actual close-while-idle sequence when changing that lifecycle; do not kill the user's Chrome to simulate failure.

`authenticated_ui_read_only` means mini-modal inspection only, with `active_generation: null`. Ask/list/export remain blocked by `rovo_layout_unverified`. `Message sent.` is not terminal response evidence. Do not create a live question to diagnose an unverified mini-modal lifecycle or switch transports to bypass this restriction.

## 6. Test conversation continuity with two small synthetic turns

Proceed only with live-test authorization, available allowance, verified legacy readiness and no unresolved request. Use a distinct synthetic marker for the run. Do not ask Rovo to remember it: one earlier test unexpectedly created a persistent memory despite instructions not to use tools. Explicitly prohibit memory writes, observe for side effects, and record any that occur.

Write the first prompt to a private UTF-8 file:

> Read-only synthetic continuity test. Reply with exactly ORBIT-5826. Do not search, use tools, save memories, or change any resources.

Send through the retained process, replacing `FIRST_PATH` with the actual private path:

```json
["ask", "--new", "--prompt-file", "FIRST_PATH"]
```

Require `execution_status: completed`, `submission_state: observed_submitted`, `continuity_status: verified`, `conversation_mode: new`, an observed `chat_id`, the exact answer and a visible completed turn. Store the ID in private evidence for comparison; the next command must not supply it. The bridge's completion check requires observed generation start, a new response, the matching user prompt, exact `Response complete.` status, no active generation and a nonempty answer.

Write the follow-up to another file:

> Using only the preceding assistant response in this conversation, return that response in lowercase. Do not search, use tools, save memories, or change any resources.

Send it as a distinct operation, preferably across separate agent turns when testing agent handle retention:

```json
["ask", "--prompt-file", "FOLLOWUP_PATH"]
```

Require the same `chat_id`, `conversation_mode: continued`, `continuity_status: verified`, answer `orbit-5826`, and one additional visible user/assistant turn. Observe the UI independently and save a cropped screenshot of the synthetic conversation. A correct marker alone is insufficient: global memory could supply it in another chat. The matched ID, transcript and turn increment establish continuity.

For a restart test, close stdin only after verified completion, wait for normal exit, and start a fresh CLI process with the same site/session/account. Submit a distinct follow-up without `--chat` or `--new`; require the same evidence. Reuse an existing verified synthetic first turn when available rather than creating it again. Plan restart as the second turn, or authorize an extra third turn if same-process continuity was also tested. A new request ID is expected. Restart acceptance does not prove recovery from sleep, expired authentication or a lost connection.

For existing-chat-to-new-chat acceptance, first export the verified synthetic chat using its observed ID. Confirm that chat is visible and New chat is enabled, then send one authorized `ask --new`. Require a distinct new ID and one new user/assistant pair. Export both chats read-only: the original must be unchanged and the saved binding must point to the new chat. For restart continuity, export the continued chat and compare the preserved first pair plus the added second pair. Read-only exports add no questions and do not change the saved binding. Keep actual IDs and transcript text out of Git.

Verify negative cases offline: wrong account/site, old records without a binding, missing/ambiguous IDs, altered history, a missing picker row, draft changes during fill, and `--new` combined with `--chat`. New-chat capture requires exactly one send request from the owned tab after Submit, and the completed turn hash and loaded count must match. Do not weaken those checks just to make an unfamiliar history layout pass.

A completed response with `continuity_status: unavailable` is still delivered. Preserve its answer and warning, stop implicit follow-up, and inspect before an explicitly authorized observed `--chat` selection. Do not resend the original prompt or silently use `--new` to hide failure.

## 7. Diagnose the failing layer, without another submission

| Observation | Next step |
|---|---|
| `chrome_debugging_unavailable` | Inspect discovery, OS/user alignment and the existing Chrome setting; verify any explicit port before a status-only attempt |
| `chrome_approval_failed` | Stop before submission; save the sanitized helper error, preserve retry state, leave other clients/prompts untouched; no helper or ask retry |
| `chrome_connection_failed` | Record phase, elapsed time, caller deadline and whether the owner actually saw/approved the prompt; no automatic endpoint change |
| Need connection evidence before any submission | One status attempt with `DEBUG=pw:browser`, stderr saved privately; no protocol tracing and no ask |
| `authentication_required` | Verify intended account and supported sign-in state; do not send to another account |
| Readiness deadline or unexpected panel | Observe the retained tab read-only; no reload or generic frontend diagnosis without evidence |
| `click_diagnostics` present | Record fixed control, allowlisted reason and `timed_out`; locate the failed phase without raw page/log leakage or retrying a question |
| Existing draft, attachment or generation | Preserve it; stop the send and inspect ownership/state |
| Attempted/uncertain submission, timeout, missing result or unresolved record | Preserve request/chat evidence; no resend, reconnect-for-retry, record deletion or transport/session bypass |
| Completed ask with `retry_safe: false` | The same turn must not be resent; a distinct authorized follow-up is allowed only after successful completion and the relevant continuity checks |
| Correct response but no retrieval proof | Report response completion separately; inspect actual tool/source/file evidence for a separately authorized retrieval test |

Use the canonical prompt for MCP eligibility, diagnostics and target-machine acceptance. MCP's guard tests and UI access do not prove direct CLI continuity; A2A is a separate qualification path. Do not create a replacement stack during a reliability investigation.

## 8. Finish with evidence and cleanup

Use a compact per-candidate record:

```text
Candidate: commit + dirty diff/file hashes; installed executable and package location
Environment: OS/Python/Chrome; build-tool versions; approved transport; caller deadline
Offline: command, exit code, passed count; package parity; doc mirrors
Live: authorized/used question count; exact scenario; JSON and UI evidence paths
Verdict: source / installed / normal-Chrome / Copilot-host / retrieval, each separately
Limits: missing evidence, unsupported layouts, skipped checks, later code changes
Cleanup: process detached; owned tabs/drafts/scaffolding removed or specifically retained
```

Keep output and evidence, even from failed tests. Close stdin and wait for detachment before cleanup. The CLI closes its idle tab when it shows exactly the last verified answer, and retains draft-bearing, uncertain or unverified tabs; that is deliberate. After a completed test, close only the known agent-created disposable tabs, preserving remote chat/request history and all user tabs. Remove only the synthetic drafts you created. Do not delete populated state directories or completion records to make the workspace look clean.

If Rovo unexpectedly creates a test memory, identify the exact entry, obtain any required deletion confirmation, remove only that entry and verify the UI result. Do not disable memory globally or delete unrelated memories. The earlier synthetic memory was removed after explicit owner approval; that approval is not reusable for other entries.

List and remove task-created build/egg-info directories and temporary edit scripts after verification; retain the candidate wheel, logs, screenshots, prompts used as evidence and request receipts. Do not sweep unrelated files or historical checkpoints. A documentation change should not trigger another live request just for a new screenshot.

Commit/push only when authorized. Before committing, check status and merge state, use explicit pathspecs and review the exact candidate diff for private data. After pushing, verify the remote commit and the changed documents; verify the canonical prompt too if it changed. Update [VALIDATION.md](VALIDATION.md) with measured results and remaining limits; update this runbook only when the method changes. Keep one canonical Copilot setup prompt rather than creating competing versions.

## Development evidence behind this runbook

| Candidate | What was measured | Limits |
|---|---|---|
| Tab/readiness fix, `a20e948` | 185 offline tests; 12 installed files and three mirrors matched; normal-Chrome tab reuse, panel reopen, closed-tab replacement and draft preservation; no Rovo question | Development Mac only; pinned isolated build unavailable |
| Continuity enhancement, `bcb1554` | 205 installed offline tests; 12 files and three mirrors matched; three live turns used one captured chat without `--chat`, including a fresh process; test memory cleanup verified | Final pre-submit/persistence refinements were verified offline after live tests; no additional live question was sent for those refinements; Copilot-host and grounded retrieval acceptance remain open |
| Click diagnostics and later continuity acceptance, `7c5f895` | 246 installed offline tests; three later authorized questions verified empty-screen new chat, existing-chat switch and restart continuation; read-only exports and saved signatures matched | An initial narrow-window startup failed before submission; expanded-window restart passed; Copilot-host and retrieval acceptance remain open |
| Narrow-window readiness, `41ca8de` | 249 installed offline tests; failing overflow regression reproduced before fix; installed startup and another status passed at narrow width; saved request unchanged; zero questions | Read-only live validation after this final fix; older post-readiness timeout remains unidentified |

These counts describe specific candidates, not permanent expected totals. Synthetic continuity without “remember” wording has passed locally, including after process restart; it has not been accepted in the actual Copilot host. Detailed current scope is recorded in [Validation status](VALIDATION.md#current-development-baseline-2026-10-23).

## Guarded Chrome approval acceptance

Use a build whose `doctor` lists `guarded Chrome prompt approval`. Verify the installed wheel includes `utils/allow.sh` and `utils/chrome_approval.py`. Offline tests must cover an existing foreign prompt, a foreign socket, a second prompt arriving before the click, changed window identity/bounds, missing prerequisites, and helper failure before any page or Submit action. Keep manual mode and MCP fallback guard tests green.

With explicit authorization and the target’s existing debugging port verified, start one retained `session` with `--chrome-port PORT --approve-chrome-prompt`. Do not run a separate approval helper. Save startup JSON and confirm authenticated idle readiness with no human click. Only if a live question is authorized, send one synthetic prompt once and verify completion. Never retry an uncertain ask. A second-agent prompt test is read-only: leave that prompt pending, start the guarded connection, require `chrome_approval_failed` before a new attachment, and verify the other prompt remains untouched. Stop only test-owned processes and close only test-owned tabs; preserve evidence outside Git. Do not change policy to manufacture a failure.
