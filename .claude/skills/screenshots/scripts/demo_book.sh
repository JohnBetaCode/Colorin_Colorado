#!/usr/bin/env bash
# Create (once) the neutral demo book "Mi mundo para colorear" and print its slug.
# Runs demo_book.py in a throwaway container of the app's image (no rebuild, no AI calls):
# books/ and data/ are mounted as usual, this folder at /skill and spike/ read-only.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
cd "$ROOT"
mounts=(-v "$HERE:/skill:ro")
# Mount spike/ only when it exists: Docker would create a missing host folder as root.
[ -d spike ] && mounts+=(-v "$ROOT/spike:/workspace/spike:ro")
docker compose run --rm --no-deps -T "${mounts[@]}" app python /skill/demo_book.py | tail -1
