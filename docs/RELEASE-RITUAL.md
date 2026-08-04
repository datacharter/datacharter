# The 12-minute release ritual — DEV-INTERNAL

Automated gates verify what we thought to encode. This ritual verifies what a
human actually touches. Run it against the RELEASE artifacts (installed wheel
+ the dmg), then commit `docs/releases/v<X.Y.Z>-verified.txt` — the release
gate warns when it's missing, and fails once the repo variable
`REQUIRE_VERIFIED=true` is set (flip it after your first ritual).

## The four rounds

1. **Claude Code round (~4 min).** Clean workspace → connect Claude Code →
   ask a data question, then a follow-up that needs memory. Confirm: answers
   come from queries (SQL chips visible), no file-hunting, `•••` where PII,
   disconnect → connect a local model → ask again.
2. **The dmg as a user (~4 min).** Gatekeeper-open the dmg. Export a result
   and close the exported file (app must survive). Quit, relaunch: no tour
   replay, About shows the real version.
3. **One governed drag-drop (~2 min).** Drag a CSV with an email column.
   Masking toggle appears in the tree; agent view shows `•••`; toggle to
   allow shows real values; toggle back.
4. **Error-copy skim (~2 min).** Skim any new error strings in the release
   diff: each says what to fix, none tells users to do something destructive,
   all are copyable in the UI.

## The verified file

```
# docs/releases/v0.24.0-verified.txt
version: 0.24.0
date: 2026-08-10
who: <name>
claude-code-round: pass
dmg-round: pass
drag-drop-round: pass
error-skim: pass
notes: <anything observed>
```

Any `fail` → fix first, re-run the ritual, then release.
