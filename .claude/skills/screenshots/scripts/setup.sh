#!/usr/bin/env bash
# Create (once) a throwaway virtualenv with Playwright, outside the repo. Uses the system Google
# Chrome (channel="chrome"), so no browser download is needed. Prints the python to use.
#   PY=$(.claude/skills/screenshots/scripts/setup.sh [venv-dir])
set -euo pipefail
VENV="${1:-${TMPDIR:-/tmp}/colorin-colorado-playwright}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV" >&2
  "$VENV/bin/pip" install -q playwright pillow >&2
fi
command -v google-chrome >/dev/null || { echo "google-chrome not found; install Chrome or run: $VENV/bin/playwright install chromium (and drop channel=\"chrome\")" >&2; exit 1; }
echo "$VENV/bin/python"
