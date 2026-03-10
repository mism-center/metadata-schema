# metadata-schema
Versioned FAIR-compliant metadata schemas and validation tools supporting model registration, discovery, and interoperability within the MISM ecosystem.

## Installation

```bash
uv add mism-registry
```

Or with pip:

```bash
pip install mism-registry
```

**Requires Python 3.10+.** No runtime dependencies — stdlib only.

## Quick Start

```python
from mism_registry import (
    Author,
    ExecutionType,
    InMemoryRegistry,
    IOSlot,
    IOSpec,
    Publication,
    Resource,
    ResourceType,
    RunEnvironment,
    register_dataset,
    register_model,
    prepare_run,
    start_run,
    complete_run,
    cancel_run,
    get_lineage,
    get_dependents,
)

# Create a registry (in-memory for now; production backends plug in via the Registry protocol)
registry = InMemoryRegistry()
```

### Register a Dataset

```python
dataset = register_dataset(
    registry,
    name="SARS-CoV-2 Spike Variants (Omicron)",
    location_uri="s3://mism-data/omicron_spike.fasta",
    format_tags=["fasta", "viral", "spike-protein", "sars-cov-2"],
    owner="team-alpha@niaid.nih.gov",
    external_ids={"genbank": "MN908947"},
    license="CC-BY-4.0",
    # Authorship & attribution
    authors=[Author(name="Alice Smith", orcid="0000-0001-2345-6789", affiliation="NIAID VRC")],
    organization="NIAID VRC",
    contact_email="alice@niaid.nih.gov",
    publications=[Publication(title="Omicron Spike Analysis", doi="10.1234/omicron")],
    funding=["NIAID U19 AI123456"],
    # Scientific context
    organisms=["SARS-CoV-2"],
    modeling_scales=["molecular"],
    domains=["structural-biology", "immunology"],
)
```

### Register a Model

Models require an `execution_type`. An `io_spec` is optional but recommended — it enables automatic input compatibility checks.

```python
model = register_model(
    registry,
    name="Viral Escape Predictor",
    location_uri="git+https://github.com/mism/escape-model@v2.0",
    execution_type=ExecutionType.PYTHON,
    version="2.0.0",
    format_tags=["escape-prediction", "mutation-analysis"],
    io_spec=IOSpec(
        inputs=(IOSlot(name="sequences", tags=("fasta", "viral")),),
        outputs=(IOSlot(name="escape_panel", tags=("csv", "escape-mutations")),),
    ),
    organisms=["SARS-CoV-2", "Homo sapiens"],
)
```

Available execution types: `DOCKER`, `CONDA`, `PYTHON`, `R`, `BINARY`, `HUGGINGFACE`, `NOTEBOOK`, `OTHER`.

### Run a Model

`prepare_run` validates that the model exists and is active, all inputs exist and are active, and (if the model has an IOSpec) that input tags satisfy the declared requirements.

```python
run = prepare_run(
    registry,
    model_id=model.id,
    input_resource_ids=[dataset.id],
    parameters={"mutation_threshold": 0.03},
    environment=RunEnvironment(platform="helx"),
    triggered_by="researcher@niaid.nih.gov",
)

# Transition through the lifecycle
run = start_run(registry, run_id=run.id)

# On completion, register outputs as first-class resources
output = Resource(
    name="Omicron Escape Panel (predicted)",
    resource_type=ResourceType.DATASET,
    location_uri=f"s3://mism-results/{run.id}/escape_panel.csv",
    format_tags=["csv", "escape-mutations", "sars-cov-2"],
)
run = complete_run(registry, run_id=run.id, output_resources=[output])
```

If execution fails instead:

```python
from mism_registry import fail_run

run = fail_run(registry, run_id=run.id, error_message="OOM on node 3")
```

To cancel a run before or during execution:

```python
run = cancel_run(registry, run_id=run.id)
```

Runs can be cancelled from `REGISTERED` or `RUNNING` state. Completed and failed runs are terminal.

### Versioning

Resources follow immutable versioning — data changes always create a new Resource with a new UUID. The original is automatically marked as superseded.

```python
from mism_registry import create_new_version, get_latest_version, get_version_history

# Publish a new version (original is marked SUPERSEDED automatically)
v2 = create_new_version(
    registry,
    original_id=dataset.id,
    location_uri="s3://mism-data/omicron_spike_v2.fasta",
    version="2.0",
    digest_sha256="abc123...",
)
# v2 inherits name, authorship, organisms, and other metadata from the original

# Follow the chain to the latest active version
latest = get_latest_version(registry, dataset.id)

# Get the full version history (oldest first)
history = get_version_history(registry, dataset.id)
```

Only metadata corrections (description, tags, contact info) are in-place mutations via `update_resource`. Any change to the underlying data requires `create_new_version`.

### Query Lineage

```python
# What produced this output?
lineage = get_lineage(registry, run.output_resource_ids[0])

# What runs consumed this dataset?
dependents = get_dependents(registry, dataset.id)
```

### Discover Resources

```python
from mism_registry import find_resources, find_runs, ResourceType

# Find all FASTA datasets
datasets = find_resources(registry, resource_type=ResourceType.DATASET, tags=["fasta"])

# Find resources by organism
sars_resources = find_resources(registry, organisms=["SARS-CoV-2"])

# Find molecular-scale resources
molecular = find_resources(registry, scales=["molecular"])

# Search by name substring (case-insensitive)
spike_data = find_resources(registry, name_contains="spike")

# Combine filters (AND logic)
results = find_resources(
    registry,
    resource_type=ResourceType.DATASET,
    tags=["fasta"],
    organisms=["SARS-CoV-2"],
    owner="team-alpha@niaid.nih.gov",
)

# Find runs by a specific model
runs = find_runs(registry, model_id=model.id)
```

## Core Concepts

### Entities

| Entity | Description |
|---|---|
| **Resource** | Anything registered: a dataset, model, or tool. Identified by UUID. Tracks status (active, superseded, archived), authorship, scientific context, and version chain pointers. |
| **Run** | Records one execution of a model — what went in, what came out, where it ran. |
| **IOSpec / IOSlot** | Optional declaration of a model's expected inputs and outputs, used for compatibility checks. |
| **RunEnvironment** | Describes the execution platform (HeLx, Biowulf, local, etc.). |
| **Author** | Frozen value object for contributor attribution (name, ORCID, affiliation, role). |
| **Publication** | Frozen value object for linked publications (title, DOI, URL, citation). |

### Resource Status

Resources have a lifecycle status:

| Status | Meaning |
|---|---|
| `ACTIVE` | Current and usable (default). Required for use in new runs. |
| `SUPERSEDED` | Replaced by a newer version. Set automatically by `create_new_version`. |
| `ARCHIVED` | Manually retired. |

### Run Lifecycle

Runs follow a state machine:

```
REGISTERED ──> RUNNING ──> COMPLETED
    │              │
    │              ├──> FAILED
    │              │
    └──────────────┴──> CANCELLED
```

### Tag-Based Matching

Resources are typed with free-form string tags (normalized to lowercase). When a model declares an IOSpec, `prepare_run` checks that each required input slot's tags are a subset of at least one provided input resource's tags.

```
Model slot requires:   ["fasta", "viral"]
Input resource has:    ["fasta", "viral", "spike-protein", "sars-cov-2"]
Result:                match (superset)
```

### Immutable Versioning

Data changes always produce a new Resource with a new UUID. The version chain is navigable in both directions:

- `new_version_of` — points backward to the predecessor
- `superseded_by` — points forward to the successor

```
v1 (SUPERSEDED) ──superseded_by──> v2 (SUPERSEDED) ──superseded_by──> v3 (ACTIVE)
                <──new_version_of──                 <──new_version_of──
```

`get_version_history` returns the full chain from any point. `get_latest_version` follows forward to the current active version.

## Postgres Backend

A production-ready Postgres backend ships as an optional extra, built on SQLAlchemy 2.0 and Alembic.

### Install

```bash
uv add "mism-registry[postgres]"
```

### Apply migrations

```bash
MISM_DAL_DATABASE_URL="postgresql+psycopg://user:pass@localhost/mism" \
  uv run alembic upgrade head
```

### Quick-start (scripts and notebooks)

```python
from mism_registry import register_dataset, find_resources
from mism_registry.backends import create_registry

registry, session = create_registry("postgresql+psycopg://user:pass@localhost/mism")

dataset = register_dataset(registry, name="My Dataset", location_uri="s3://bucket/data.csv")

session.commit()
session.close()
```

### Production usage (per-request session management)

```python
from mism_registry.backends import PostgresRegistry, create_session_factory

SessionFactory = create_session_factory("postgresql+psycopg://user:pass@localhost/mism")

# Example FastAPI dependency
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

`PostgresRegistry` calls `flush()` but never `commit()` — the caller controls transaction boundaries. All operation functions (`register_dataset`, `prepare_run`, etc.) work identically with `PostgresRegistry` as with `InMemoryRegistry`.

## Custom Storage Backends

The library defines a `Registry` protocol. Implement it to plug in any other storage backend:

```python
from mism_registry import Registry, Resource, Run

class MyCustomRegistry:
    """Implements the Registry protocol against a custom store."""

    def register_resource(self, resource: Resource) -> Resource: ...
    def get_resource(self, resource_id: str) -> Resource: ...
    def find_resources(
        self, *, resource_type=None, tags=None, owner=None,
        name_contains=None, organisms=None, scales=None,
    ) -> list[Resource]: ...
    def update_resource(self, resource: Resource) -> Resource: ...
    def create_run(self, run: Run) -> Run: ...
    def get_run(self, run_id: str) -> Run: ...
    def update_run(self, run: Run) -> Run: ...
    def find_runs(self, *, model_id=None, input_resource_id=None, status=None) -> list[Run]: ...
    def get_lineage(self, resource_id: str) -> list[Run]: ...
    def get_dependents(self, resource_id: str) -> list[Run]: ...
    def get_latest_version(self, resource_id: str) -> Resource | None: ...
    def get_version_history(self, resource_id: str) -> list[Resource]: ...
```

All operation functions (`register_dataset`, `prepare_run`, `create_new_version`, etc.) accept any object satisfying this protocol.

## Error Handling

All exceptions inherit from `MismRegistryError`:

```python
from mism_registry import (
    MismRegistryError,        # base
    ValidationError,          # invalid field values or status checks
    ResourceNotFoundError,    # unknown resource ID
    RunNotFoundError,         # unknown run ID
    DuplicateResourceError,   # re-registering same ID
    IOSpecMismatchError,      # input tags don't match model requirements
    InvalidStateTransitionError,  # e.g., completing an already-failed run
)
```

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies (creates .venv automatically)
uv sync --group dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=mism_registry --cov-report=term-missing

# Type check
uv run mypy src/mism_registry/

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

## Further Reading

For a detailed walkthrough with more examples — including a full end-to-end pipeline, lineage tracing patterns, and testing recipes — see **[docs/guide.md](docs/guide.md)**.

## License

MIT
