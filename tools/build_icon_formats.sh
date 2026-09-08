#!/usr/bin/env bash
# Rebuild images/AppIcon.icns (macOS) and images/AppIcon.ico (Windows) from
# images/AppIcon.png. Run after tools/make_icon.py. Needs macOS (sips/iconutil).
set -euo pipefail
cd "$(dirname "$0")/.."

MASTER="images/AppIcon.png"
TMPDIR="$(mktemp -d)"
ICONSET="$TMPDIR/AppIcon.iconset"
mkdir -p "$ICONSET"

sips -z 16 16   "$MASTER" --out "$ICONSET/icon_16x16.png"      >/dev/null
sips -z 32 32   "$MASTER" --out "$ICONSET/icon_16x16@2x.png"   >/dev/null
sips -z 32 32   "$MASTER" --out "$ICONSET/icon_32x32.png"      >/dev/null
sips -z 64 64   "$MASTER" --out "$ICONSET/icon_32x32@2x.png"   >/dev/null
sips -z 128 128 "$MASTER" --out "$ICONSET/icon_128x128.png"    >/dev/null
sips -z 256 256 "$MASTER" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$MASTER" --out "$ICONSET/icon_256x256.png"    >/dev/null
sips -z 512 512 "$MASTER" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$MASTER" --out "$ICONSET/icon_512x512.png"    >/dev/null
cp "$MASTER" "$ICONSET/icon_512x512@2x.png"

iconutil -c icns "$ICONSET" -o images/AppIcon.icns
rm -rf "$TMPDIR"

uv run python -c "
from PIL import Image
Image.open('$MASTER').save('images/AppIcon.ico',
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
"

echo "wrote images/AppIcon.icns and images/AppIcon.ico"
