# Initial repository privacy review

The repository starts from a fresh Git history and a selected set of source files. The session workspace is not imported wholesale.

Included: current Python package, synthetic tests, portable operator/architecture documentation, Copilot skill, upstream license and attribution. Excluded: original Node prototype, browser profiles, cookies, credentials, local environments, screenshots, raw test output, conversation exports, usage reports, personal domains, configured accounts, private repository lists and account-specific research notes.

A real conversation UUID in a test fixture was replaced with a synthetic UUID. The raw test report containing a developer's absolute paths was replaced with a portable validation summary. Runtime code resolves user-specific paths and identities from the current machine and explicit inputs; local output can therefore contain personal information even though no such values are embedded in the source.

The pre-push source scan with Gitleaks found no secrets. Checks for known development identifiers and machine-specific paths passed, the wheel contained only the intended package and license files, and all 20 installed-command/unit tests passed. Staged contents and the fresh Git history are also scanned before upload. No scanner guarantees absence of every possible sensitive value. Keep generated runtime data outside version control.

GitHub account ownership and commit attribution remain normal repository metadata. Use a GitHub no-reply email for commits. Repository visibility must remain private until explicitly authorized otherwise.
