# Copilot setup prompt

Copy the text below into Copilot Agent mode under Copilot.

```text
Install Rovo Relay from https://github.com/rm0nroe/rovo-relay and configure it for this project.

1. Read README.md and AGENTS.md. Detect my OS and shell. Clone into my normal development folder, create a Python virtual environment, install the package, and run `rovo-relay --json doctor`. Preserve existing local work.

2. Copy the included `.github/skills/rovo-relay/SKILL.md` into my current project without overwriting an existing skill. Ensure Copilot can invoke the installed `rovo-relay` executable.

3. Connect to my existing signed-in normal Chrome session with Jira and Rovo using the documented requirements. Preserve tabs and unsent drafts. Do not extract cookies, start an isolated browser, or bypass browser or account restrictions. Ask for my Jira URL and expected account if needed.

4. Run the account-bound `status` command. Once it succeeds, confirm available Rovo credits and ask me for a repository/file that Rovo already reads successfully by hand.

5. Submit ONE question through `rovo-relay` with `--github-source on`, asking Rovo to summarize that file and provide its source link. Use a private prompt file. Never automatically retry an uncertain submission or erase request records to bypass a guard.

Composio, Atlassian MCP, and an official Rovo CLI are not dependencies. Do not install them, enable paid usage, or change connector permissions.

Complete every unblocked step. Report installation, skill setup, authenticated browser access, and actual GitHub retrieval separately. A completed response alone does not prove successful retrieval. Stop after the one live test and report any remaining blocker.
```

Other-machine browser access and code retrieval remain unverified until this test passes.
