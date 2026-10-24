#!/bin/bash
# Vendored click sequence, guarded for this CLI's attachment.
# Internal interface: allow.sh CLI_PID VERIFIED_PORT. Never run as a standalone sweeper.
set -euo pipefail
exec /usr/bin/python3 "$(dirname "$0")/chrome_approval.py" "$@"
