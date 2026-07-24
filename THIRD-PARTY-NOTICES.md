# Third-party notices

DataCharter is distributed under [Apache-2.0](LICENSE). It depends on, and its
wheel bundles a pre-built web UI that includes, third-party open-source software.
Each component remains under its own license; the copyright and license notices
below are provided in acknowledgement. Full license texts are available in each
project's repository.

## Python runtime dependencies

| Component | License |
| --- | --- |
| [DuckDB](https://github.com/duckdb/duckdb) | MIT |
| [PyYAML](https://github.com/yaml/pyyaml) | MIT |
| [pydantic](https://github.com/pydantic/pydantic) | MIT |
| [FastAPI](https://github.com/fastapi/fastapi) | MIT |
| [Starlette](https://github.com/encode/starlette) (via FastAPI) | BSD-3-Clause |
| [uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause |
| [httpx](https://github.com/encode/httpx) | BSD-3-Clause |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | BSD-3-Clause |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 |
| [keyring](https://github.com/jaraco/keyring) | MIT |
| [ruamel.yaml](https://sourceforge.net/projects/ruamel-yaml/) | MIT |

Optional extra (`datacharter[snowflake]`):

| Component | License |
| --- | --- |
| [snowflake-connector-python](https://github.com/snowflakedb/snowflake-connector-python) | Apache-2.0 |

DuckDB extensions (BigQuery, SQL Server, Iceberg, Delta, httpfs, etc.) are fetched
by DuckDB at runtime from its extension repositories and are not bundled here.

## Bundled web UI (included in the wheel)

| Component | License |
| --- | --- |
| [React](https://github.com/facebook/react) / react-dom | MIT |
| [Monaco Editor](https://github.com/microsoft/monaco-editor) | MIT |
| [@monaco-editor/react](https://github.com/suren-atoyan/monaco-react) | MIT |
| [TanStack Table](https://github.com/TanStack/table) | MIT |
| [TanStack Virtual](https://github.com/TanStack/virtual) | MIT |
| [Vega](https://github.com/vega/vega) | BSD-3-Clause |
| [Vega-Lite](https://github.com/vega/vega-lite) | BSD-3-Clause |
| [vega-embed](https://github.com/vega/vega-embed) | BSD-3-Clause |

## Development and CI tools (not distributed)

Build and test tooling — Vite, TypeScript, pytest, pytest-asyncio, ruff, and
[VidaiMock](https://github.com/vidaiUK/VidaiMock) (Apache-2.0, the mock LLM server
used by the end-to-end tests) — is used to develop and test DataCharter and is
not included in the distributed package.

> A complete, auto-generated license bundle (with full texts) can be produced at
> build time from `pip-licenses` and the npm `license-checker`; this file is the
> curated summary.
