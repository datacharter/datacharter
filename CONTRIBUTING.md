# Contributing to DataCharter

Thanks for your interest in DataCharter. Contributions of all kinds — bug
reports, docs, tests, and code — are welcome. The project is licensed under
[Apache-2.0](LICENSE); contributions are accepted under the same license.

## Ways to contribute

- **Report a bug or request a feature** — open an issue with steps to reproduce
  or a clear description of the use case.
- **Improve docs** — fixes to the guides under `docs/` and the README are always
  welcome.
- **Send a pull request** — for anything beyond a trivial fix, open (or comment
  on) an issue first so we can agree on the approach before you invest the work.

## Development setup

DataCharter is one Python package with a bundled web UI. You need Python 3.11+
and [uv](https://docs.astral.sh/uv/); UI work additionally needs Node.

```sh
# Python environment (creates .venv)
uv sync

# Run the app from source
uv run datacharter serve

# Web UI (only if you're changing the frontend)
cd ui && npm ci && npm run build
```

## Tests and linting

Every change lands with tests, and the working tree must be lint-clean. These
are the same commands CI runs:

```sh
uv run pytest -q                 # unit tests (fast; the default set)
uv run pytest -m integration -q  # integration tests (require Docker)
uv run pytest -m e2e -q          # end-to-end (see below)
uv run ruff check .              # lint
cd ui && npm run build           # type-check + build the UI
```

The end-to-end agent test drives a real
[VidaiMock](https://github.com/vidaiUK/VidaiMock) server (an Apache-2.0 mock LLM);
it skips unless `VIDAIMOCK_BIN` points at the binary or `vidaimock` is on `PATH`.

Write tests that describe behavior, keep unit tests fast, and put anything that
needs Docker or a live server behind the `integration` / `e2e` markers so the
default run stays quick.

## Commit and pull-request conventions

- **[Conventional Commits](https://www.conventionalcommits.org/)**:
  `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`. Keep the subject
  under ~72 characters, imperative mood.
- Small, focused commits over large omnibus ones. Every commit should build and
  pass tests so history stays bisectable.
- Never commit secrets, tokens, or real hostnames — in code, tests, or fixtures.
- Keep the PR scoped to one change; describe the "why," not just the "what."

## Developer Certificate of Origin (sign-off required)

DataCharter uses the **Developer Certificate of Origin (DCO)** instead of a CLA.
Every commit must be signed off, certifying that you wrote the change (or
otherwise have the right to submit it under Apache-2.0). This is a lightweight,
one-time habit — no separate agreement to sign.

Add the sign-off automatically with the `-s` flag:

```sh
git commit -s -m "fix: correct off-by-one in row cap"
```

That appends a line matching your configured `git` name and email:

```
Signed-off-by: Jane Developer <jane@example.com>
```

Use your real name and a valid email. If you forget the sign-off on your last
commit, amend it with `git commit --amend -s`; for a whole branch, use
`git rebase --signoff <base>`. PRs whose commits are not signed off cannot be
merged.

By signing off, you agree to the DCO, version 1.1:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```
