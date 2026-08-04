#!/usr/bin/env bash
# The full pre-release gate, one command, zero manual steps. Run from the
# repo that will be released (the public checkout), on the release machine
# (needs the real `claude` binary + Chrome for the journey).
#
#   bash scripts/release_gate.sh
#
# Builds the artifacts, verifies them (wheel gate + browser journey + live
# Claude Code round + local-LLM round), and WRITES the verified file that
# release.yml requires — docs/releases/v<version>-verified.txt. Any failure
# leaves no file and exits non-zero: the release cannot proceed.
set -euo pipefail

cd "$(dirname "$0")/.."
say() { printf '\n== %s ==\n' "$*"; }

say "build (UI + wheel)"
bash scripts/build_ui.sh
uv build

VERSION=$(python3 -c "
import re, pathlib
print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('src/datacharter/__init__.py').read_text()).group(1))")
WHEEL="dist/datacharter-${VERSION}-py3-none-any.whl"
test -f "$WHEEL" || { echo "wheel not built: $WHEEL"; exit 1; }

say "install $WHEEL into a clean venv"
GATE_VENV=$(mktemp -d)/venv
uv venv "$GATE_VENV" -q
uv pip install -q --python "$GATE_VENV/bin/python" "$WHEEL"
DC_BIN="$GATE_VENV/bin/datacharter"

say "wheel gate (battery + MCP stdio)"
WHEEL_GATE_OUT=$("$GATE_VENV/bin/python" scripts/wheel_gate.py 2>&1) || {
  echo "$WHEEL_GATE_OUT"; exit 1; }
echo "$WHEEL_GATE_OUT" | tail -3

say "browser journey on the wheel"
WS=$(mktemp -d)/journey-ws
"$DC_BIN" init "$WS" >/dev/null
PORT=$((20000 + RANDOM % 20000))
"$DC_BIN" serve "$WS" --port "$PORT" >/dev/null 2>&1 &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null || true' EXIT
for _ in $(seq 30); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 1
done
JOURNEY_OUT=$(JOURNEY_CHANNEL="${JOURNEY_CHANNEL:-chrome}" node scripts/journey.mjs --port "$PORT" 2>&1) || {
  echo "$JOURNEY_OUT"; exit 1; }
echo "$JOURNEY_OUT" | tail -3
kill $SERVE_PID 2>/dev/null || true
wait $SERVE_PID 2>/dev/null || true

say "live Claude Code round (real claude) + local-LLM round"
LIVE_OUT=$("$GATE_VENV/bin/python" scripts/claude_live_check.py --bin "$DC_BIN" 2>&1) || {
  echo "$LIVE_OUT"; exit 1; }
echo "$LIVE_OUT"

say "write docs/releases/v${VERSION}-verified.txt"
mkdir -p docs/releases
{
  echo "version: ${VERSION}"
  echo "date: $(date -u +%Y-%m-%d)"
  echo "who: release_gate.sh (automated; run on the release machine)"
  echo "wheel-gate: pass"
  echo "journey: pass"
  echo "claude-code-round: pass"
  echo "notes: |"
  echo "$LIVE_OUT" | sed 's/^/  /'
} > "docs/releases/v${VERSION}-verified.txt"
cat "docs/releases/v${VERSION}-verified.txt"

echo
echo "release gate PASSED for v${VERSION} — commit the verified file, then tag."
