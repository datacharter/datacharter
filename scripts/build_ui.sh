#!/usr/bin/env bash
# Build the web UI into the Python package so the wheel is self-contained.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here/ui"
npm ci
npm run build
dest="$here/src/datacharter/server/static"
rm -rf "$dest"
cp -r dist "$dest"
echo "UI built into src/datacharter/server/static"
