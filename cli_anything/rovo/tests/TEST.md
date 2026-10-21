# Test plan and evidence boundary

Run the installed-command suite with `CLI_ANYTHING_FORCE_INSTALLED=1`. The offline suite must not contact Rovo, create browser sessions or spend provider credits. Argument fixtures use example domains and a synthetic conversation UUID.

Unit checks cover URL/account/session validation, site locking, durable uncertain-delivery state, completion after a matching new turn, output bounds and PNG count/size/signature/name policy. Subprocess checks cover installed command resolution, packaged skill discovery, JSON errors, dry-run, image arguments, source choices and conversation IDs.

The recorded development live results and remaining gates are summarized in `docs/VALIDATION.md` at the repository root. Raw logs and personal identifiers are intentionally not included. A clean package installation and this suite are required before pushing the initial repository; live tests are not repeated for documentation sanitization.
