---
title: Governance gates for data pipelines
description: Enforce your data contract inside Dagster, Airflow, or any CI — fail the run when the data drifts, an assertion breaks, or a change widens what an agent can see.
---

[Home](index.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [CLI](cli.html) &middot; [Security](security.html) &middot; [Provenance](provenance.html)

# Governance gates for data pipelines

DataCharter's contract isn't only for the agent surface — it's a checkable spec
you can enforce wherever your data moves. Three exit-coded commands are the gates;
wire them into Dagster, Airflow, or any CI, and a violation fails the run.

## The gates

| Command | Fails when | Use it |
| --- | --- | --- |
| `datacharter test` | a charter data assertion breaks | after a load/transform — does the data still meet the contract? |
| `datacharter drift` | declared tables/columns/PII no longer match the sources | on a schedule / after a schema migration |
| `datacharter access diff --fail-on widened --against git:main` | a charter edit **widens** what an agent can see | on every pull request (offline; no credentials) |

Each exits non-zero on a violation, so any orchestrator that checks exit codes
gates on it. Point them at the workspace with the charter.

## Dagster

An asset check (or a plain `@op`) that runs the contract test and fails the
materialization on a violation:

```python
import subprocess
from dagster import asset_check, AssetCheckResult

@asset_check(asset="customers")
def contract_holds():
    r = subprocess.run(["datacharter", "test", "/workspace"], capture_output=True, text=True)
    return AssetCheckResult(passed=r.returncode == 0,
                            metadata={"output": r.stdout + r.stderr})
```

Prefer a hard failure that stops downstream assets? Raise instead:

```python
from dagster import op

@op
def datacharter_gate():
    if subprocess.run(["datacharter", "drift", "/workspace"]).returncode != 0:
        raise Exception("DataCharter drift gate failed — the schema no longer matches the contract")
```

## Airflow

A `BashOperator` is the whole integration — the exit code becomes the task result:

```python
from airflow.operators.bash import BashOperator

contract_test = BashOperator(
    task_id="datacharter_contract_test",
    bash_command="datacharter test /opt/airflow/workspace",
)
# ... load >> contract_test >> publish
```

Or the TaskFlow API, if you want the output in the logs:

```python
from airflow.decorators import task
import subprocess

@task
def datacharter_gate():
    r = subprocess.run(["datacharter", "test", "/opt/airflow/workspace"],
                       capture_output=True, text=True)
    print(r.stdout, r.stderr)
    if r.returncode != 0:
        raise RuntimeError("DataCharter contract test failed")
```

## CI (pull requests)

The access-widening gate is best on every PR — it's offline (no database, no
credentials) and catches a contract change that would expose more to an agent
before it merges:

```yaml
# .github/workflows/governance.yml
- run: pipx run datacharter access diff --against git:origin/main --fail-on widened
```

## Why gate here

Governance that only lives at query time can be out-run by a bad deploy: a schema
migration drops a masked column, a transform reshapes a table, a charter edit
quietly widens access. Running these gates in the pipeline and in CI moves the
catch **left** — the contract is enforced as the data and the contract change, not
only when an agent asks.

Next: [Verifiable provenance →](provenance.html)
