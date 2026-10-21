# Copilot setup prompt

This is the single setup prompt for a first installation. Copy the text below into Copilot Agent mode on the target machine.

```text
Install Rovo Relay from https://github.com/rm0nroe/rovo-relay and configure it for this project.

1. Read README.md and AGENTS.md. Detect my OS and shell. Clone into my normal development folder, create a Python virtual environment, install the package, and run `rovo-relay --json doctor`. Preserve existing local work.

2. Copy the included `.github/skills/ask-rovo/SKILL.md` into my current project without overwriting an existing skill. Verify the skill is available as `/ask-rovo` and can invoke the installed `rovo-relay` executable.

3. Connect to my existing signed-in normal Chrome session with Jira and Rovo using the documented requirements. Preserve tabs and unsent drafts. Do not extract cookies, start an isolated browser, or bypass browser or account restrictions. Ask for my Jira URL and expected account if needed. Before attaching, check that Chrome is version 144 or newer and the CLI runs in the same OS/user environment as Chrome (not a separate WSL, container, or remote environment). Guide me to `chrome://inspect/#remote-debugging` in that Chrome to explicitly enable remote debugging if organizational policy allows it. Explain that this grants control of the Chrome session, not just Rovo. Keep Chrome open, run status, and have me approve the connection prompt. If the setting is missing or managed, report that blocker; do not change policy, restart Chrome with debugging flags, or fabricate a DevToolsActivePort file.

4. Run the account-bound `status` command. Once it succeeds, confirm available Rovo credits and ask me for a repository/file that Rovo already reads successfully by hand.

5. Submit ONE question through `rovo-relay` with `--github-source on`, asking Rovo to summarize that file and provide its source link. Use a private prompt file. Never automatically retry an uncertain submission or erase request records to bypass a guard.

Composio, Atlassian MCP, and an official Rovo CLI are not dependencies. Do not install them, enable paid usage, or change connector permissions.

Complete every unblocked step. Report installation, skill setup, authenticated browser access, and actual GitHub retrieval separately. A completed response alone does not prove successful retrieval. Stop after the one live test and report any remaining blocker.

If blocked, provide a short, copyable report for the Rovo Relay developer containing:
- OS, shell, Python version, installed Rovo Relay version, and checkout commit if available; Chrome version/channel and whether the terminal runs locally, in WSL, a container, or a remote session.
- Failed step: install, /ask-rovo discovery, doctor, browser status, or live question.
- Exact command, exit code, and error/JSON output; mark unavailable details rather than guessing.
- Whether Chrome remote debugging is enabled, missing or managed; whether Chrome requested approval; and whether Jira/Rovo is open and signed in.
- Whether a prompt was submitted, whether Rovo answered in the browser, and any submission_state or retry_safe values. If delivery is uncertain, say so explicitly.

Redact account emails, private site/repo names, personal paths, tokens, and proprietary content from the report. Preserve error wording and JSON field names around redactions. Never include cookies or browser profiles. If the error is visible only in Chrome or VS Code, include a cropped, redacted screenshot if available, or describe the visible message. Do not rerun a live request just to collect diagnostics. Leave the chat and request records intact, and never retry a possibly submitted prompt automatically.
```

Other-machine browser access and code retrieval remain unverified until this test passes.
