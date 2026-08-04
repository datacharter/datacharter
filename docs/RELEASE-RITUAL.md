# The release gate — automated, zero manual steps

`release.yml` refuses to publish unless `docs/releases/v<X.Y.Z>-verified.txt`
exists (repo variable `REQUIRE_VERIFIED=true`). That file is written only by
the gate itself, and only when every round passes:

```
bash scripts/release_gate.sh   # run in the public checkout, on the release machine
```

What it runs, in order — any failure stops the release:

1. **Build** — UI bundle + wheel.
2. **Wheel gate** — the 9-check runtime battery + MCP stdio handshake against
   the installed wheel (`scripts/wheel_gate.py`).
3. **Browser journey** — the 11-step first-session walk in a real browser
   against the served wheel, console-clean (`scripts/journey.mjs`): first-run,
   demo, tour + no-replay-after-reload, query, every chart kind, export
   (app survives), drag-drop of a PII csv, agent-view masking, the coarse
   toggle both ways, backend surface.
4. **Live Claude Code round** — the REAL `claude` binary through the
   tool-surface assertion, a data question answered via governed tool calls,
   a value-detected-PII question (raw values must never appear in any event),
   and a follow-up on the same session proving memory
   (`scripts/claude_live_check.py`). Requires the release machine's Claude
   subscription — this is why the round runs here, not in CI.
5. **Local-LLM round** — if a local runtime (Ollama etc.) is up, connect it
   through `/api/agent/config` and get a real answer; skipped cleanly if not.

The verified file embeds the live-check report. CI re-verifies everything it
can independently (fake-claude harness, journey, wheel gate, frozen-build
gates) — the file covers the two rounds only this machine can run.

**Still manual, until signing lands:** the Gatekeeper "open anyway" dance on
a fresh Mac exists because the dmg is unsigned — automating that away means
enrolling Apple Developer certs (`APPLE_CERT_P12` + notary secrets in the
repo; the workflow steps are already stubbed in desktop.yml).
