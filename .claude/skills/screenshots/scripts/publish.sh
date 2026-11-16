#!/usr/bin/env bash
# Copy reviewed captures into docs/images/ under the names the docs link to (ui-<screen>.png),
# resized to 1280 px wide and quantized to 255 colours (palette PNG, like the current files).
#   publish.sh <shots-dir> [docs/images] [screen ...]     e.g. publish.sh "$OUT" docs/images workbench
# With no screen names, every <screen>.png in <shots-dir> is published. Prints old -> new sizes.
set -euo pipefail
SRC="${1:?shots dir}"; DST="${2:-docs/images}"; shift $(( $# >= 2 ? 2 : $# ))
if [ $# -eq 0 ]; then set -- $(cd "$SRC" && ls *.png | sed 's/\.png$//'); fi
mkdir -p "$DST"
PY="${PY:-python3}"
for n in "$@"; do
  f="$SRC/$n.png"; out="$DST/ui-$n.png"
  [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
  before=$( [ -f "$out" ] && stat -c %s "$out" || echo 0 )
  if command -v convert >/dev/null; then
    convert "$f" -resize '1280x>' -colors 255 "$out"
  else
    "$PY" - "$f" "$out" <<'PYEOF'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGB")
if im.width > 1280:
    im = im.resize((1280, round(im.height * 1280 / im.width)), Image.LANCZOS)
im.quantize(colors=255, method=Image.Quantize.MEDIANCUT).save(sys.argv[2], optimize=True)
PYEOF
  fi
  echo "wrote $out ($before -> $(stat -c %s "$out") bytes)"
done
