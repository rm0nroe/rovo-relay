# Test plan and evidence boundary

Run the installed-command suite with `CLI_ANYTHING_FORCE_INSTALLED=1`. The offline suite must not contact Rovo, create browser sessions or spend provider credits. Argument fixtures use example domains and a synthetic conversation UUID.

Unit checks cover URL/account/session validation, site locking, durable uncertain-delivery state, completion after a matching new turn, output bounds and PNG count/size/signature/name policy. Subprocess checks cover installed command resolution, packaged skill discovery, JSON errors, dry-run, image arguments, source choices and conversation IDs.

Persistent-session tests reuse synthetic Playwright boundaries to verify one attachment across commands, fresh tab/account/composer/delivery checks, lock release while idle, no reconnect after failure, startup flushing and JSON framing, immutable binding, malformed input and stdin-prompt rejection, recoverable preparation errors, terminal uncertain sends/timeouts, EOF/signals and cleanup failures. Human REPL reuse is exercised without a terminal or browser. Installed subprocess checks also cover session help, doctor capability discovery and dry-run startup. No browser fixtures or live Rovo questions are needed.

Explicit Chrome port cases verify range validation before attachment, fixed loopback WebSocket construction, connection reuse, one-shot/REPL routing, immutable port selection, dry-run without attachment and no automatic endpoint fallback. Live acceptance is separately documented in `docs/VALIDATION.md`; the offline suite does not use a live debugging port.

The recorded development live results and remaining gates are summarized in `docs/VALIDATION.md` at the repository root. Raw logs and personal identifiers are intentionally not included. A clean package installation and this suite are required before pushing the initial repository; live tests are not repeated for documentation sanitization.
