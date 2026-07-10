# Developer Guide

A hands-on walkthrough of `mism-registry` for application developers. This guide
covers every day-to-day operation with runnable examples you can copy-paste into
a Python shell.

> **Tip:** Every snippet below works as-is with `InMemoryRegistry`. Swap it out
> for the Postgres backend (covered at the end) and nothing else changes.

---

## Table of Contents

- [Installation](#installation)
- [30-Second Overview](#30-second-overview)
- [Registering Resources](#registering-resources)
  - [Datasets](#datasets)
  - [Models](#models)
  - [Tools](#tools)
- [Running Models](#running-models)
  - [Prepare a Run](#1-prepare-a-run)
  - [Start a Run](#2-start-a-run)
  - [Complete a Run](#3-complete-a-run)
  - [Fail a Run](#handling-failures)
  - [Cancel a Run](#cancelling-a-run)
- [Discovering Resources and Runs](#discovering-resources-and-runs)
- [Tracing Lineage](#tracing-lineage)
- [Versioning Resources](#versioning-resources)
- [Error Handling](#error-handling)
- [Using the Postgres Backend](#using-the-postgres-backend)
- [Testing with the Registry](#testing-with-the-registry)
- [Quick Reference](#quick-reference)

---

## Installation

```bash
# with uv
uv add mism-registry

# with pip
pip install mism-registry
```

The core library has **zero runtime dependencies** (stdlib only, Python 3.10+).

For Postgres support, install the optional extra:

```bash
uv add "mism-registry[postgres]"
```

---

## 30-Second Overview

The registry tracks three things:

1. **Resources** — datasets, models, or tools that your team publishes.
2. **Runs** — records of a model being executed: what went in, what came out.
3. **Lineage** — the graph that connects resources through runs.

Everything goes through plain functions that accept a `registry` object.
The registry is your storage backend — swap it without touching business logic.

```python
from mism_registry import InMemoryRegistry

registry = InMemoryRegistry()
```

---

## Registering Resources

### Datasets

A dataset is any data artifact — a FASTA file, a CSV, an image archive. At
minimum you need a `name` and a `location_uri` (where the data lives).

```python
from mism_registry import register_dataset

dataset = register_dataset(
    registry,
    name="SARS-CoV-2 Spike Variants (Omicron)",
    location_uri="s3://mism-data/omicron_spike.fasta",
)
print(dataset.id)       # auto-generated UUID
print(dataset.version_status)   # ResourceVersionStatus.ACTIVE
```

That's the minimum. In practice you'll want to add context so others can find
and trust the data:

```python
from datetime import date
from mism_registry import Author, Publication, register_dataset

dataset = register_dataset(
    registry,
    name="SARS-CoV-2 Spike Variants (Omicron)",
    location_uri="s3://mism-data/omicron_spike.fasta",
    # Tags make it discoverable and enable IOSpec matching
    format_tags=["fasta", "viral", "spike-protein"],
    # Authorship
    authors=[
        Author(
            name="Alice Smith",
            orcid="0000-0001-2345-6789",
            affiliation="NIAID VRC",
        ),
        Author(name="Bob Jones", role="data-curator"),
    ],
    organization="NIAID VRC",
    contact_email="alice@niaid.nih.gov",
    publications=[
        Publication(title="Omicron Spike Analysis", doi="10.1234/omicron"),
    ],
    funding=["NIAID U19 AI123456"],
    # Scientific context
    organisms=["SARS-CoV-2"],
    model_scales=["molecular"],
    domains=["structural-biology", "immunology"],
    # Integrity & provenance
    version="1.0",
    digest_sha256="a1b2c3d4e5f6...",
    size_bytes=14_200_000,
    external_ids={"genbank": "MN908947"},
    license="CC-BY-4.0",
    owner="team-alpha@niaid.nih.gov",
    date_published=date(2026, 1, 15),
)
```

### Models

Models are executable resources. They require an `execution_type` so the
platform knows how to run them.

```python
from mism_registry import ExecutionType, IOSlot, IOSpec, register_model

model = register_model(
    registry,
    name="Viral Escape Predictor",
    location_uri="git+https://github.com/mism/escape-model@v2.0",
    execution_type=ExecutionType.PYTHON,
    version="2.0.0",
    # IOSpec declares what this model consumes and produces
    io_spec=IOSpec(
        inputs=(
            IOSlot(name="sequences", tags=("fasta", "viral")),
        ),
        outputs=(
            IOSlot(name="escape_panel", tags=("csv", "escape-mutations")),
        ),
    ),
    organisms=["SARS-CoV-2", "Homo sapiens"],
)
```

**Why add an IOSpec?** When you later call `prepare_run`, the library
automatically checks that every required input slot can be satisfied by at
least one of the input datasets you provide. This catches mistakes before
execution starts.

The matching rule is straightforward — **the input resource's `format_tags`
must be a superset of the slot's `tags`**:

```
Slot requires:    ["fasta", "viral"]
Resource has:     ["fasta", "viral", "spike-protein"]
Result:           match (superset)
```

**Available execution types:**
`DOCKER`, `CONDA`, `PYTHON`, `R`, `BINARY`, `HUGGINGFACE`, `NOTEBOOK`, `OTHER`

### Tools

Tools are registered the same way as models — just pass
`resource_type=ResourceType.TOOL`:

```python
from mism_registry import ResourceType, register_model

tool = register_model(
    registry,
    name="FASTA Quality Checker",
    location_uri="docker://mism/qa-tools:latest",
    execution_type=ExecutionType.DOCKER,
    resource_type=ResourceType.TOOL,
    io_spec=IOSpec(
        inputs=(IOSlot(name="raw_data", tags=("fasta",)),),
        outputs=(IOSlot(name="report", tags=("json", "quality-report")),),
    ),
)
```

---

## Running Models

Runs track the execution of a model from start to finish. They follow a
simple state machine:

```
REGISTERED ──> RUNNING ──> COMPLETED
    |              |
    |              +-----> FAILED
    |              |
    +──────────────+-----> CANCELLED
```

### 1. Prepare a Run

`prepare_run` creates a run in `REGISTERED` status. It validates that:

- The model exists and is **active**
- All input resources exist and are **active**
- Input tags satisfy the model's IOSpec (if one is declared)

```python
from mism_registry import RunEnvironment, prepare_run

run = prepare_run(
    registry,
    model_id=model.id,
    input_resource_ids=[dataset.id],
    parameters={"mutation_threshold": 0.03, "window_size": 50},
    environment=RunEnvironment(
        platform="helx",
        container_uri="docker://mism/escape-model:v2.0",
        hardware_description="4x A100 GPU",
    ),
    triggered_by="researcher@niaid.nih.gov",
    notes="Batch run for Q1 2026 variant surveillance",
)

print(run.status)            # RunStatus.REGISTERED
print(run.model_version)     # "2.0.0" (denormalized from model)
print(run.input_resource_ids)  # [dataset.id]
```

### 2. Start a Run

When your execution engine picks up the job:

```python
from mism_registry import start_run

run = start_run(registry, run_id=run.id)
print(run.status)      # RunStatus.RUNNING
print(run.started_at)  # timestamp
```

### 3. Complete a Run

When execution finishes, register the output resources and mark the run
complete in one call:

```python
from mism_registry import Resource, ResourceType, complete_run

output = Resource(
    name="Omicron Escape Panel (predicted)",
    resource_type=ResourceType.DATASET,
    location_uri=f"s3://mism-results/{run.id}/escape_panel.csv",
    format_tags=["csv", "escape-mutations", "sars-cov-2"],
)

run = complete_run(registry, run_id=run.id, output_resources=[output])
print(run.status)              # RunStatus.COMPLETED
print(run.output_resource_ids) # [<UUID of newly registered output>]
print(run.completed_at)        # timestamp
```

Each output resource in the list is automatically registered in the registry
as a first-class resource with its own UUID.

**Multiple outputs work too:**

```python
summary = Resource(
    name="Run Summary Stats",
    resource_type=ResourceType.DATASET,
    location_uri=f"s3://mism-results/{run.id}/summary.json",
    format_tags=["json", "run-summary"],
)
detailed = Resource(
    name="Per-Residue Escape Scores",
    resource_type=ResourceType.DATASET,
    location_uri=f"s3://mism-results/{run.id}/per_residue.csv",
    format_tags=["csv", "escape-mutations", "per-residue"],
)

run = complete_run(registry, run_id=run.id, output_resources=[summary, detailed])
# run.output_resource_ids now has 2 UUIDs
```

### Handling Failures

If a run fails, record what went wrong:

```python
from mism_registry import fail_run

run = fail_run(
    registry,
    run_id=run.id,
    error_message="OOM killed on node gpu-03 after 4h12m",
    log_uri="s3://mism-logs/runs/abc123/stderr.log",
)
print(run.status)  # RunStatus.FAILED
```

### Cancelling a Run

Runs can be cancelled from `REGISTERED` or `RUNNING`:

```python
from mism_registry import cancel_run

run = cancel_run(registry, run_id=run.id)
print(run.status)  # RunStatus.CANCELLED
```

Completed, failed, and cancelled runs are terminal — no further transitions
are allowed.

---

## Discovering Resources and Runs

### Search Resources

`find_resources` supports several filters. When you combine them they use
**AND** logic (all conditions must match):

```python
from mism_registry import find_resources, ResourceType

# Everything in the registry
all_resources = find_resources(registry)

# All datasets
datasets = find_resources(registry, resource_type=ResourceType.DATASET)

# Datasets tagged with "fasta" (resource must have ALL listed tags)
fasta_data = find_resources(
    registry,
    resource_type=ResourceType.DATASET,
    tags=["fasta"],
)

# Resources about SARS-CoV-2 (must match at least ONE listed organism)
sars = find_resources(registry, organisms=["SARS-CoV-2"])

# Molecular-scale resources
molecular = find_resources(registry, scales=["molecular"])

# Search by name (case-insensitive substring match)
spike = find_resources(registry, name_contains="spike")

# By owner
team_data = find_resources(registry, owner="team-alpha@niaid.nih.gov")

# Combine everything
results = find_resources(
    registry,
    resource_type=ResourceType.DATASET,
    tags=["fasta", "viral"],
    organisms=["SARS-CoV-2"],
    scales=["molecular"],
    owner="team-alpha@niaid.nih.gov",
)
```

### Search Runs

```python
from mism_registry import find_runs, RunStatus

# All runs for a model
model_runs = find_runs(registry, model_id=model.id)

# Runs that used a specific dataset as input
runs_using_d1 = find_runs(registry, input_resource_id=dataset.id)

# Failed runs
failed = find_runs(registry, status=RunStatus.FAILED)

# Combine: failed runs for a specific model
failed_for_model = find_runs(
    registry,
    model_id=model.id,
    status=RunStatus.FAILED,
)
```

---

## Tracing Lineage

Lineage lets you trace the provenance graph in both directions:

```python
from mism_registry import get_lineage, get_dependents
```

### Backward: "What produced this resource?"

```python
lineage = get_lineage(registry, output_resource_id)
# Returns list[Run] — runs that have this resource in their output_resource_ids

for run in lineage:
    print(f"Produced by model {run.model_id}, run {run.id}")
    print(f"  Inputs:  {run.input_resource_ids}")
    print(f"  Status:  {run.status}")
```

### Forward: "What consumed this resource?"

```python
dependents = get_dependents(registry, dataset.id)
# Returns list[Run] — runs that have this resource in their input_resource_ids

for run in dependents:
    print(f"Consumed by model {run.model_id}, run {run.id}")
```

### Walking a Pipeline

For a multi-step pipeline like `D1 -> M1 -> D2 -> M2 -> D3`, you can trace the
full chain:

```python
def trace_full_lineage(registry, resource_id, depth=0):
    """Recursively trace backward through the pipeline."""
    runs = get_lineage(registry, resource_id)
    for run in runs:
        model = registry.get_resource(run.model_id)
        print(f"{'  ' * depth}Produced by: {model.name} (run {run.id[:8]}...)")
        for input_id in run.input_resource_ids:
            inp = registry.get_resource(input_id)
            print(f"{'  ' * (depth + 1)}Input: {inp.name}")
            trace_full_lineage(registry, input_id, depth + 2)

trace_full_lineage(registry, final_output_id)
```

---

## Versioning Resources

Resources use **immutable versioning** — if the underlying data changes, you
create a new Resource with a new UUID. The old version is automatically marked
`SUPERSEDED`.

### Creating a New Version

```python
from mism_registry import create_new_version

v2 = create_new_version(
    registry,
    original_id=dataset.id,
    location_uri="s3://mism-data/omicron_spike_v2.fasta",
    version="2.0",
    digest_sha256="f6e5d4c3b2a1...",
    size_bytes=15_800_000,
)
```

The new resource **inherits** from the original:
- Name, resource type, authorship, organisms, domains, scales, license,
  execution type (for models), and more.

You can **override** specific fields:

```python
v3 = create_new_version(
    registry,
    original_id=v2.id,
    location_uri="s3://mism-data/omicron_spike_v3.fasta",
    version="3.0",
    description="Added XBB.1.5 sublineage sequences",
    format_tags=["fasta", "viral", "spike-protein", "xbb"],
)
```

### Navigating the Version Chain

```python
from mism_registry import get_latest_version, get_version_history

# Follow the chain forward to the current active version
latest = get_latest_version(registry, dataset.id)
print(latest.version)  # "3.0"

# Get the full chain, oldest first
history = get_version_history(registry, dataset.id)
for r in history:
    print(f"  {r.version} ({r.version_status.value}) — {r.id[:8]}...")
# Output:
#   1.0 (superseded) — a1b2c3d4...
#   2.0 (superseded) — e5f6a7b8...
#   3.0 (active)     — c9d0e1f2...
```

The chain is navigable from **any** version — `get_version_history` walks
backward to the root, then forward to collect everything.

### When to Version vs. Update

| Action | Use |
|---|---|
| Fix a typo in the description | `registry.update_resource(resource)` |
| Correct contact email or tags | `registry.update_resource(resource)` |
| Add new sequences to a dataset | `create_new_version(...)` |
| Retrain a model on new data | `create_new_version(...)` |
| Fix a bug in model code | `create_new_version(...)` |

---

## Error Handling

All exceptions inherit from `MismRegistryError` so you can catch broadly or
narrowly:

```python
from mism_registry import (
    MismRegistryError,
    ResourceNotFoundError,
    RunNotFoundError,
    ValidationError,
    DuplicateResourceError,
    IOSpecMismatchError,
    InvalidStateTransitionError,
)
```

### Common Patterns

**Resource not found:**

```python
try:
    r = registry.get_resource("nonexistent-id")
except ResourceNotFoundError as e:
    print(f"No resource with ID: {e.resource_id}")
```

**IOSpec mismatch (wrong input tags):**

```python
try:
    run = prepare_run(
        registry,
        model_id=model.id,
        input_resource_ids=[wrong_format_dataset.id],
    )
except IOSpecMismatchError as e:
    print(f"Input tags don't match model requirements: {e}")
```

**Invalid state transition:**

```python
try:
    cancel_run(registry, run_id=completed_run.id)
except InvalidStateTransitionError as e:
    print(f"Can't cancel a completed run: {e}")
```

**Catch everything from this library:**

```python
try:
    do_something(registry)
except MismRegistryError as e:
    log.error(f"Registry error: {e}")
```

---

## Using the Postgres Backend

For production use, the library ships a Postgres-backed registry using
SQLAlchemy and Alembic.

### Setup

```bash
# Install with postgres extras
uv add "mism-registry[postgres]"

# Start Postgres (Docker)
docker run -d --name mism-pg \
  -e POSTGRES_DB=mism \
  -e POSTGRES_USER=mism \
  -e POSTGRES_PASSWORD=mism \
  -p 5432:5432 \
  postgres:16

# Apply database migrations
MISM_DAL_DATABASE_URL="postgresql+psycopg://mism:mism@localhost/mism" \
  uv run alembic upgrade head
```

### Usage

**Quick start (scripts / notebooks):**

```python
from mism_registry import register_dataset
from mism_registry.backends import create_registry

registry, session = create_registry("postgresql+psycopg://mism:mism@localhost/mism")

dataset = register_dataset(
    registry,
    name="My Dataset",
    location_uri="s3://bucket/data.csv",
    format_tags=["csv"],
)

session.commit()   # persist to Postgres
session.close()
```

**Production (web app with proper session management):**

```python
from mism_registry.backends import Base, PostgresRegistry, create_session_factory

SessionFactory = create_session_factory("postgresql+psycopg://mism:mism@localhost/mism")

# Per-request pattern (e.g., FastAPI dependency)
def get_registry():
    session = SessionFactory()
    try:
        registry = PostgresRegistry(session)
        yield registry
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

The `PostgresRegistry` calls `flush()` but **never** `commit()` — your
application controls transaction boundaries.

---

## Testing with the Registry

`InMemoryRegistry` is purpose-built for tests. No database needed.

```python
import pytest
from mism_registry import (
    InMemoryRegistry,
    ExecutionType,
    IOSlot,
    IOSpec,
    register_dataset,
    register_model,
    prepare_run,
    start_run,
    complete_run,
    Resource,
    ResourceType,
)


@pytest.fixture()
def registry():
    return InMemoryRegistry()


@pytest.fixture()
def sample_dataset(registry):
    return register_dataset(
        registry,
        name="Test Data",
        location_uri="s3://test/data.csv",
        format_tags=["csv", "timeseries"],
        owner="test-user",
    )


@pytest.fixture()
def sample_model(registry):
    return register_model(
        registry,
        name="Test Model",
        location_uri="docker://registry/model:v1",
        execution_type=ExecutionType.DOCKER,
        io_spec=IOSpec(
            inputs=(IOSlot(name="input_data", tags=("csv",)),),
            outputs=(IOSlot(name="predictions", tags=("json",)),),
        ),
    )


def test_run_lifecycle(registry, sample_dataset, sample_model):
    run = prepare_run(
        registry,
        model_id=sample_model.id,
        input_resource_ids=[sample_dataset.id],
    )
    run = start_run(registry, run_id=run.id)

    output = Resource(
        name="Predictions",
        resource_type=ResourceType.DATASET,
        location_uri="s3://test/predictions.json",
        format_tags=["json"],
    )
    run = complete_run(registry, run_id=run.id, output_resources=[output])

    assert run.status.value == "completed"
    assert len(run.output_resource_ids) == 1
```

---

## Quick Reference

### Operations

| Function | Description |
|---|---|
| `register_dataset(registry, *, name, location_uri, ...)` | Register a dataset |
| `register_model(registry, *, name, location_uri, execution_type, ...)` | Register a model or tool |
| `create_new_version(registry, *, original_id, location_uri, ...)` | Create new version (supersedes original) |
| `prepare_run(registry, *, model_id, input_resource_ids, ...)` | Validate inputs and create a run |
| `start_run(registry, *, run_id)` | Mark run as running |
| `complete_run(registry, *, run_id, output_resources)` | Register outputs and mark run completed |
| `fail_run(registry, *, run_id, error_message, ...)` | Mark run as failed |
| `cancel_run(registry, *, run_id)` | Cancel a run |
| `find_resources(registry, *, resource_type, tags, owner, ...)` | Search resources |
| `find_runs(registry, *, model_id, input_resource_id, status)` | Search runs |
| `get_lineage(registry, resource_id)` | Runs that produced a resource |
| `get_dependents(registry, resource_id)` | Runs that consumed a resource |
| `get_latest_version(registry, resource_id)` | Follow version chain to current |
| `get_version_history(registry, resource_id)` | Full version chain (oldest first) |

### Enums

| Enum | Values |
|---|---|
| `ResourceType` | `DATASET`, `MODEL`, `TOOL` |
| `ExecutionType` | `DOCKER`, `CONDA`, `PIP`, `PYTHON`, `R`, `BINARY`, `HUGGINGFACE`, `NOTEBOOK`, `SINGULARITY`, `NEXTFLOW`, `SNAKEMAKE`, `JUPYTER`, `NATIVE`, `OTHER` |
| `ResourceVersionStatus` | `ACTIVE`, `SUPERSEDED`, `ARCHIVED` |
| `ResourceRegistrationStatus` | `DRAFT`, `ANNOTATING`, `ANNOTATION_FAILED`, `PENDING_REVIEW`, `REJECTED`, `APPROVED` |
| `RunStatus` | `REGISTERED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED` |

### Exceptions

| Exception | When |
|---|---|
| `ResourceNotFoundError` | Resource ID not in registry |
| `RunNotFoundError` | Run ID not in registry |
| `ValidationError` | Invalid fields, inactive resource, wrong resource type |
| `DuplicateResourceError` | Registering a resource with an existing ID |
| `IOSpecMismatchError` | Input tags don't satisfy model's IOSpec |
| `InvalidStateTransitionError` | Illegal run status transition |
