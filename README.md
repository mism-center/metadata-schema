# mism-registry

FAIR-ready metadata registry for the MISM (Multiscale Immune Systems Modeling) ecosystem. Register biomedical models and datasets, track execution, and query data lineage.

## Installation

```bash
pip install mism-registry
```

For development (includes pytest, mypy, ruff):

```bash
pip install -e ".[dev]"
```

**Requires Python 3.10+.** No runtime dependencies — stdlib only.

## Quick Start

```python
from mism_registry import (
    InMemoryRegistry,
    ExecutionType,
    IOSlot,
    IOSpec,
    Resource,
    ResourceType,
    RunEnvironment,
    register_dataset,
    register_model,
    prepare_run,
    start_run,
    complete_run,
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
)
```

### Register a Model

Models require an `execution_type`. An `io_spec` is optional but recommended — it enables automatic input compatibility checks.

```python
model = register_model(
    registry,
    name="Viral Escape Predictor",
    location_uri="git+https://github.com/mism/escape-model@v2.0",
    execution_type=ExecutionType.PYTHON_PACKAGE,
    format_tags=["escape-prediction", "mutation-analysis"],
    io_spec=IOSpec(
        inputs=(IOSlot(name="sequences", tags=("fasta", "viral")),),
        outputs=(IOSlot(name="escape_panel", tags=("csv", "escape-mutations")),),
    ),
)
```

### Run a Model

`prepare_run` validates that the model exists, all inputs exist, and (if the model has an IOSpec) that input tags satisfy the declared requirements.

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

# Find runs by a specific model
runs = find_runs(registry, model_id=model.id)
```

## Core Concepts

### Entities

| Entity | Description |
|---|---|
| **Resource** | Anything registered: a dataset, model, or tool. Identified by UUID. |
| **Run** | Records one execution of a model — what went in, what came out, where it ran. |
| **IOSpec / IOSlot** | Optional declaration of a model's expected inputs and outputs, used for compatibility checks. |
| **RunEnvironment** | Describes the execution platform (HeLx, Biowulf, local, etc.). |

### Run Lifecycle

Runs follow a state machine:

```
REGISTERED ──→ RUNNING ──→ COMPLETED
    │              │
    │              ├──→ FAILED
    │              │
    └──────────────┴──→ CANCELLED
```

### Tag-Based Matching

Resources are typed with free-form string tags (normalized to lowercase). When a model declares an IOSpec, `prepare_run` checks that each required input slot's tags are a subset of at least one provided input resource's tags.

```
Model slot requires:   ["fasta", "viral"]
Input resource has:    ["fasta", "viral", "spike-protein", "sars-cov-2"]
Result:                match (superset)
```

## Custom Storage Backends

The library defines a `Registry` protocol. Implement it to plug in any storage backend:

```python
from mism_registry import Registry, Resource, Run

class PostgresRegistry:
    """Implements the Registry protocol against PostgreSQL."""

    def register_resource(self, resource: Resource) -> Resource: ...
    def get_resource(self, resource_id: str) -> Resource: ...
    def find_resources(self, *, resource_type=None, tags=None, owner=None, name_contains=None) -> list[Resource]: ...
    def update_resource(self, resource: Resource) -> Resource: ...
    def create_run(self, run: Run) -> Run: ...
    def get_run(self, run_id: str) -> Run: ...
    def update_run(self, run: Run) -> Run: ...
    def find_runs(self, *, model_id=None, input_resource_id=None, status=None) -> list[Run]: ...
    def get_lineage(self, resource_id: str) -> list[Run]: ...
    def get_dependents(self, resource_id: str) -> list[Run]: ...
```

All operation functions (`register_dataset`, `prepare_run`, etc.) accept any object satisfying this protocol.

## Error Handling

All exceptions inherit from `MismRegistryError`:

```python
from mism_registry import (
    MismRegistryError,        # base
    ValidationError,          # invalid field values
    ResourceNotFoundError,    # unknown resource ID
    RunNotFoundError,         # unknown run ID
    DuplicateResourceError,   # re-registering same ID
    IOSpecMismatchError,      # input tags don't match model requirements
    InvalidStateTransitionError,  # e.g., completing an already-failed run
)
```

## Development

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src/mism_registry/

# Lint
ruff check src/ tests/
```

## License

MIT
