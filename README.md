# metadata-schema

Versioned, FAIR-ready metadata schema and validation library for the MISM
ecosystem. Provides the data model, validation rules, and storage interface
for registering biomedical models and datasets, tracking their execution,
and querying their lineage.

This is the **lowest layer** of the MISM platform. APIs, UIs, pipeline
orchestrators, and export tools build on top of it. It does **not** orchestrate
execution, serve HTTP, render UI, or enforce authorization — see
[“What this layer is not”](#what-this-layer-is-not).

## Installation

```bash
uv add mism-registry
```

Or with pip:

```bash
pip install mism-registry
```

**Requires Python 3.10+.** Core has no runtime dependencies (stdlib only).
The Postgres backend is an optional extra (see [Postgres Backend](#postgres-backend)).

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

# In-memory backend for quick experimentation; swap PostgresRegistry in for production.
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
    authors=[
        Author(name="Alice Smith", orcid="0000-0001-2345-6789", affiliation="NIAID VRC"),
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
)
```

### Register a Model

Models require an `execution_type`. An `io_spec` is optional but recommended —
it enables automatic input compatibility checks at `prepare_run` time.

```python
model = register_model(
    registry,
    name="Viral Escape Predictor",
    location_uri="git+https://github.com/mism/escape-model@v2.0",
    execution_type=ExecutionType.PYTHON,
    execution_ref="escape_model:v2.0",      # docker tag, pip spec, HF slug, etc.
    version="2.0.0",
    format_tags=["escape-prediction", "mutation-analysis"],
    io_spec=IOSpec(
        inputs=(IOSlot(name="sequences", tags=("fasta", "viral")),),
        outputs=(IOSlot(name="escape_panel", tags=("csv", "escape-mutations")),),
        parameters_schema={                  # JSON Schema, descriptive only
            "type": "object",
            "properties": {"mutation_threshold": {"type": "number"}},
        },
    ),
    organisms=["SARS-CoV-2", "Homo sapiens"],
)
```

Available execution types: `DOCKER`, `CONDA`, `PIP`, `PYTHON`, `R`, `BINARY`,
`HUGGINGFACE`, `NOTEBOOK`, `SINGULARITY`, `NEXTFLOW`, `SNAKEMAKE`, `JUPYTER`,
`NATIVE`, `OTHER`. (Maps to the annotation package's `execution.environment_kind`.)

### Run a Model

`prepare_run` validates that the model exists and is active, all inputs exist
and are active, and (if the model has an IOSpec) that input tags satisfy the
declared requirements.

```python
run = prepare_run(
    registry,
    model_id=model.id,
    input_resource_ids=[dataset.id],
    parameters={"mutation_threshold": 0.03},
    environment=RunEnvironment(
        platform="helx",
        container_uri="ghcr.io/mism/escape-model:v2.0",
        container_digest="sha256:abc...",
        hardware_description="4xA100, 128GB RAM",
    ),
    triggered_by="researcher@niaid.nih.gov",
)

# Lifecycle transitions
run = start_run(registry, run_id=run.id)

# On success, register outputs as first-class resources
output = Resource(
    name="Omicron Escape Panel (predicted)",
    resource_type=ResourceType.DATASET,
    location_uri=f"s3://mism-results/{run.id}/escape_panel.csv",
    format_tags=["csv", "escape-mutations", "sars-cov-2"],
)
run = complete_run(registry, run_id=run.id, output_resources=[output])
```

If execution fails:

```python
from mism_registry import fail_run

run = fail_run(registry, run_id=run.id, error_message="OOM on node 3")
```

To cancel a run before or during execution:

```python
run = cancel_run(registry, run_id=run.id)
```

Runs can be cancelled from `REGISTERED` or `RUNNING`. `COMPLETED` and `FAILED`
are terminal.

### Versioning

Resources are immutable. Any change to underlying data creates a new Resource
with a new UUID; the original is automatically marked `SUPERSEDED`. Only
metadata corrections (description tweaks, adding tags, fixing contact email)
are permitted in-place via `update_resource` — they do **not** change the ID
or the digest.

```python
from mism_registry import create_new_version, get_latest_version, get_version_history

v2 = create_new_version(
    registry,
    original_id=dataset.id,
    location_uri="s3://mism-data/omicron_spike_v2.fasta",
    version="2.0",
    digest_sha256="abc123...",
)
# v2 inherits authorship, organisms, license, etc. from the original.

latest = get_latest_version(registry, dataset.id)
history = get_version_history(registry, dataset.id)  # oldest → newest
```

### Lineage

```python
# What runs produced this output?
lineage = get_lineage(registry, run.output_resource_ids[0])

# What runs consumed this dataset?
dependents = get_dependents(registry, dataset.id)
```

### Discover Resources

```python
from mism_registry import find_resources, find_runs, ResourceType

# Type + tag filter
datasets = find_resources(registry, resource_type=ResourceType.DATASET, tags=["fasta"])

# Scientific filters
sars = find_resources(registry, organisms=["SARS-CoV-2"])
molecular = find_resources(registry, scales=["molecular"])
imm = find_resources(registry, domains=["immunology"])

# Substring + combined (AND logic)
results = find_resources(
    registry,
    resource_type=ResourceType.DATASET,
    tags=["fasta"],
    organisms=["SARS-CoV-2"],
    name_contains="spike",
    owner="team-alpha@niaid.nih.gov",
)

# Runs by model
runs = find_runs(registry, model_id=model.id)
```

### Enriched Run Details (UI helper)

`get_model_run_details` returns a model plus all its runs with their input
and output Resources hydrated — designed for a "Model Runs" page that needs
everything in a single call.

```python
from mism_registry import get_model_run_details, RunStatus

summary = get_model_run_details(registry, model_id=model.id)
# summary.model            → Resource
# summary.runs             → list[ModelRunDetail]
# detail.run               → Run
# detail.input_resources   → list[Resource]   (hydrated)
# detail.output_resources  → list[Resource]   (hydrated)

# Optional status filter
failed = get_model_run_details(registry, model_id=model.id, status=RunStatus.FAILED)
```

### Full-Text Search (Postgres backend)

The Postgres backend supports full-text search with field filters and
aggregations. The in-memory backend does **not** implement this — use
`find_resources` instead.

```python
from mism_registry import FieldFilter, SearchQuery
from mism_registry.backends import PostgresRegistry

query = SearchQuery(
    text="spike protein",
    filters=(
        FieldFilter(field="resource_type", op="eq", value="dataset"),
        FieldFilter(field="organisms", op="overlap", value=["SARS-CoV-2"]),
        FieldFilter(field="created_at", op="gte", value="2025-01-01T00:00:00Z"),
    ),
    agg_fields=("organisms", "format_tags"),
    sort_field="_score",
    sort_order="desc",
    limit=25,
    offset=0,
)
result = registry.search_resources(query)
# result.total       → int
# result.resources   → list[Resource]
# result.scores      → list[float] | None
# result.aggs        → dict[str, list[AggBucket]]
```

`FILTERABLE_FIELDS` and `AGGREGATABLE_FIELDS` enumerate which fields the
service layer should permit; consume them when building API validators.

## Core Concepts

### Entities

| Entity | Description |
|---|---|
| **Resource** | Anything registered: dataset, model, or tool. UUID-identified. Tracks version lifecycle (`version_status`), registration workflow (`registration_status`), authorship, scientific context, version chain, and execution metadata. |
| **Run** | One execution of a model. Records inputs, outputs, parameters, environment, status, timestamps, error message, log URI. |
| **IOSpec / IOSlot** | Optional declaration of a model's expected inputs and outputs, plus a JSON-Schema `parameters_schema` (descriptive). Used for tag-based compatibility checks. |
| **RunEnvironment** | Where and how a run executed: platform, container URI/digest, conda env, hardware, plus a free-form `extra` dict. |
| **Author** | Frozen value object: `name`, `orcid`, `affiliation`, `role`. |
| **Contact** | Frozen value object: `name`, `role`, `email`, `affiliation`. Who to reach *now* (vs. `Author` = who wrote it). |
| **Publication** | Frozen value object: `title`, `doi`, `pmid`, `url`, `citation`. |
| **RelatedResource** | Frozen value object: `qualifier` (e.g. `bqmodel:isDerivedFrom`), `scheme`, `value`. Links to prior models / data. |
| **Dependency / Container / Compute / EntryPoint / TestSpec** | Value objects describing execution (schema.md Section B): runtime/system deps, container recipes, compute needs, invocable commands, test harness. |
| **IODetail** | Rich I/O characterization (schema.md Section C): `parameters`, `initial_conditions`, `data_inputs`, `outputs`, `experiment_protocol`. Distinct from `IOSpec` (which drives the run handshake). |
| **ModelRunDetail / ModelRunSummary** | Composite return types for `get_model_run_details` — UI-friendly enriched run views. |

### Resource Field Reference

Required fields are the absolute minimum for registration. Recommended fields
materially improve discoverability and FAIR compliance. Optional fields are
supported but not pushed.

| Group | Field | Tier | Notes |
|---|---|---|---|
| Identity | `id` | auto | UUID. |
| | `name` | required | Human-readable. |
| | `short_description` | recommended | One-line summary (schema.md `model.short_description`). |
| | `description` | recommended | What/why this resource is (schema.md `model.long_description`). |
| | `resource_type` | required | `DATASET`, `MODEL`, `TOOL`. |
| | `version` | recommended | Semver or free-form. |
| | `version_status` | auto | Version lifecycle: `ACTIVE`, `SUPERSEDED`, `ARCHIVED`. |
| | `registration_status` | auto | Registration workflow: `DRAFT` … `APPROVED` (see below). Defaults to `APPROVED` for programmatic registration. |
| | `new_version_of`, `superseded_by` | auto | Set by `create_new_version`. |
| Attribution | `authors` | recommended | Ordered list of `Author` (who wrote it). |
| | `contacts` | optional | List of `Contact` (who to reach now). |
| | `organization` | recommended | Lab / department / institution. |
| | `contact_email` | optional | |
| | `publications` | optional | List of `Publication`. |
| | `related_resources` | optional | List of `RelatedResource` (derived-from / version-of links). |
| | `funding` | recommended | Grant numbers / acknowledgments (`list[str]`). |
| Scientific | `organisms` | recommended | e.g., `SARS-CoV-2`, `Homo sapiens` (schema.md `biology.species`). |
| | `model_scales` | recommended | `molecular`, `cellular`, `tissue`, `organ`, `organism`, `population`. |
| | `domains` | optional | `structural-biology`, `immunology`, etc. (schema.md `biology.topic_category`). |
| | `date_published` | optional | When first made available externally (distinct from `created_at`). |
| Model characterization | `model_class` | optional | MAMO labels, e.g. `agent-based model`. Value-only (ontology IRIs dropped). |
| | `formalism` | optional | MAMO/KISAO labels, e.g. `ODE`, `stochastic`. |
| | `determinism` | optional | `deterministic`, `stochastic`, `hybrid`, `unknown` (default). |
| | `time_dynamics` | optional | `continuous`, `discrete`, `event-driven`, `static`, `unknown`. |
| | `spatial` | optional | `non-spatial`, `well-mixed`, `1D`…`3D`, `lattice`, `unknown`. |
| | `multiscale` | optional | `bool \| None`. |
| Biology | `infectious_agents` | optional | Pathogen(s) of study. |
| | `health_conditions` | optional | Disease / clinical indication (MONDO/HPO/DOID labels). |
| | `biological_processes` | optional | GO labels. |
| | `molecular_entities` | optional | ChEBI labels (small molecules, ions, drugs). |
| | `proteins_genes` | optional | Free-text protein/gene names. |
| Location & integrity | `location_uri` | required | iRODS path, `s3://`, `git+https://`, HF slug, etc. |
| | `format_tags` | recommended | Auto-normalized: lowercased, stripped, deduped, sorted. |
| | `digest_sha256`, `size_bytes` | optional | Populated automatically on iRODS ingest when available. |
| | `external_ids` | optional | Cross-refs: `{"doi": ..., "pdb": ..., "huggingface": ...}`. |
| | `license` | recommended | SPDX identifier. |
| Execution (model/tool) | `execution_type` | required for model/tool | Enum (see above). Maps to `execution.environment_kind`. |
| | `execution_ref` | recommended | Image tag, pip spec, HF slug, etc. |
| | `io_spec` | recommended | Tag-based input/output contract (run handshake). |
| | `execution_status` | optional | `characterized`, `partially_characterized`, `not_determined`. |
| | `language_name`, `language_version` | optional | e.g. `Python`, `>=3.10`. |
| | `dependencies` | optional | List of `Dependency` (runtime/optional/system). |
| | `containers` | optional | List of `Container`. |
| | `compute` | optional | `Compute` — cpu/mem/gpu/parallelism/runtime. |
| | `entry_points` | optional | List of `EntryPoint` (invocable commands). |
| | `tests` | optional | `TestSpec` — framework + invocation. |
| | `execution_notes` | optional | Free text. |
| I/O detail | `io` | optional | `IODetail` — parameters, initial conditions, data inputs, outputs, experiment protocol (schema.md Section C). |
| System | `owner` | optional | Informational; real authz lives in OpenFGA. |
| | `metadata` | optional | Domain-specific JSON-serializable catch-all. |
| | `created_at`, `updated_at` | auto | UTC. |

### Resource Version Status

`version_status` tracks whether this is the current version of a resource.

| Status | Meaning |
|---|---|
| `ACTIVE` | Current and usable (default). Required for use in new runs. |
| `SUPERSEDED` | Replaced by a newer version. Set automatically by `create_new_version`. |
| `ARCHIVED` | Manually retired. |

### Registration Status

`registration_status` tracks the AI-augmented registration workflow: a user
uploads a model and gives it a title, an agent job generates the
metadata-package, a human reviews it, and on approval the resource becomes
searchable and executable. `prepare_run` requires the model to be `APPROVED`.

| Status | Meaning |
|---|---|
| `DRAFT` | Uploaded + titled; resource created, no metadata-package yet. |
| `ANNOTATING` | Agent job is generating the metadata-package. |
| `ANNOTATION_FAILED` | Agent job failed; needs retry / attention. |
| `PENDING_REVIEW` | Metadata-package ready for human review. |
| `REJECTED` | Reviewer sent it back for changes. |
| `APPROVED` | Reviewed & approved; searchable + executable. |

```
DRAFT ──> ANNOTATING ──> PENDING_REVIEW ──> APPROVED
                │               │  ▲
                ├──> ANNOTATION_FAILED      │
                │                           │
                └───────────  REJECTED ─────┘   (re-review after fixes)
```

Programmatic `register_dataset` / `register_model` default to `APPROVED`
(immediately usable). The UX/agent flow sets `DRAFT` explicitly and advances
the state via `set_registration_status`, which enforces the transition machine
above (e.g. you cannot skip straight from `DRAFT` to `APPROVED`, and `APPROVED`
is terminal):

```python
from mism_registry import set_registration_status, ResourceRegistrationStatus

# Agent job finished building the metadata-package:
set_registration_status(
    registry,
    resource_id=model.id,
    target=ResourceRegistrationStatus.PENDING_REVIEW,
)
# Illegal jumps raise InvalidStateTransitionError.
```

### Run Lifecycle

```
REGISTERED ──> RUNNING ──> COMPLETED
    │              │
    │              ├──> FAILED
    │              │
    └──────────────┴──> CANCELLED
```

### Tag-Based Matching

`format_tags` are normalized (lowercased, stripped, deduplicated, sorted) by
the `Resource` constructor. `IOSlot.tags` are normalized the same way.

When a model declares an `IOSpec`, `prepare_run` checks that **for each
required input slot, at least one provided input resource's tags are a
superset of the slot's tags**. Optional slots are skipped if no input matches.

```
Model slot requires:   ["fasta", "viral"]
Input resource has:    ["fasta", "viral", "spike-protein", "sars-cov-2"]
Result:                match (superset)
```

If the model has no IOSpec, `prepare_run` succeeds with a warning. Soft
enforcement — the system nudges toward better metadata without blocking.

### Immutable Versioning

Data changes always produce a new `Resource` with a new UUID. The version
chain is navigable in both directions:

- `new_version_of` — points backward to the predecessor.
- `superseded_by` — points forward to the successor.

```
v1 (SUPERSEDED) ──superseded_by──> v2 (SUPERSEDED) ──superseded_by──> v3 (ACTIVE)
                <──new_version_of──                 <──new_version_of──
```

`get_version_history` returns the full chain. `get_latest_version` follows
forward to the current `ACTIVE` version.

## Postgres Backend

A production-ready Postgres backend ships as an optional extra, built on
SQLAlchemy 2.0 + Alembic. JSON/JSONB columns hold nested structures
(authors, contacts, publications, related_resources, IOSpec, dependencies,
containers, compute, entry_points, tests, io, RunEnvironment, metadata);
array columns hold tag-shaped fields (`format_tags`, `organisms`,
`model_scales`, `domains`, `model_class`, `formalism`, `infectious_agents`,
`health_conditions`, `biological_processes`, `molecular_entities`,
`proteins_genes`, `input_resource_ids`).

### Install

```bash
uv add "mism-registry[postgres]"
```

### Apply Migrations

```bash
MISM_DAL_DATABASE_URL="postgresql+psycopg://user:pass@localhost/mism" \
  uv run alembic upgrade head
```

### Quick-Start (scripts and notebooks)

```python
from mism_registry import register_dataset, find_resources
from mism_registry.backends import create_registry

registry, session = create_registry("postgresql+psycopg://user:pass@localhost/mism")

dataset = register_dataset(registry, name="My Dataset", location_uri="s3://bucket/data.csv")

session.commit()
session.close()
```

### Production Usage (per-request session management)

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

`PostgresRegistry` calls `flush()` but never `commit()` — the caller controls
transaction boundaries. All operation functions (`register_dataset`,
`prepare_run`, etc.) work identically with `PostgresRegistry` and
`InMemoryRegistry`.

## Custom Storage Backends

`Registry` is a `Protocol` (structural interface). Any backend satisfying it
plugs in unchanged.

```python
from datetime import date
from mism_registry import Registry, Resource, Run, RunStatus
from mism_registry.run_detail import ModelRunSummary

class MyCustomRegistry:
    """Implements the Registry protocol against a custom store."""

    def register_resource(self, resource: Resource) -> Resource: ...
    def get_resource(self, resource_id: str) -> Resource: ...
    def find_resources(
        self, *,
        resource_type=None, tags=None, owner=None, name_contains=None,
        organisms=None, scales=None, domains=None, version_status=None,
        date_published_after: date | None = None,
        date_published_before: date | None = None,
    ) -> list[Resource]: ...
    def update_resource(self, resource: Resource) -> Resource: ...
    def create_run(self, run: Run) -> Run: ...
    def get_run(self, run_id: str) -> Run: ...
    def update_run(self, run: Run) -> Run: ...
    def find_runs(self, *, model_id=None, input_resource_id=None, status=None) -> list[Run]: ...
    def get_lineage(self, resource_id: str) -> list[Run]: ...
    def get_dependents(self, resource_id: str) -> list[Run]: ...
    def get_model_run_details(
        self, model_id: str, *, status: RunStatus | None = None,
    ) -> ModelRunSummary: ...
    def get_latest_version(self, resource_id: str) -> Resource | None: ...
    def get_version_history(self, resource_id: str) -> list[Resource]: ...
```

`search_resources(SearchQuery) -> SearchResult` is **optional** — only the
Postgres backend currently implements full-text search. The service layer
should detect backend type and route accordingly.

## Error Handling

All exceptions inherit from `MismRegistryError`:

```python
from mism_registry import (
    MismRegistryError,            # base
    ValidationError,              # invalid field values, status checks
    ResourceNotFoundError,        # unknown resource ID
    RunNotFoundError,             # unknown run ID
    DuplicateResourceError,       # re-registering same ID
    IOSpecMismatchError,          # input tags don't match model requirements
    InvalidStateTransitionError,  # e.g. completing an already-failed run
)
```

## Architecture Notes

A small set of opinions you should know if you build on top of this layer:

- **FAIR-ready, not FAIR-bloated.** Every field maps to a FAIR concern, but
  most fields are optional at registration. Registration must stay
  low-friction; richer metadata is encouraged via tooling, not blocked at the
  schema level.
- **Schema simplicity over expressiveness.** Datasets, models, and tools are
  one entity (`Resource`) with a `resource_type` discriminator. Domain-specific
  fields live in `metadata` (a typed catch-all dict) until they reach
  near-universal use, at which point they're promoted to first-class fields
  (as `authors`, `organisms`, etc. were).
- **Execution agnostic.** The DAL records that a run happened, what went in,
  what came out, and where. It does not orchestrate execution. HeLx, Biowulf,
  AWS Batch, etc. are described, not prescribed.
- **Tags over ontologies (for now).** Free-form lowercase tags with
  superset-based matching. Ontology grounding is an upgrade path, not a
  requirement, and does not require schema changes.
- **Immutable resources.** Provenance never lies. Data changes → new Resource
  with a new ID. Metadata corrections only mutate `description`, `tags`, etc.
  — never the digest.
- **Authorization boundary.** The DAL does not call OpenFGA. The service
  layer authorizes before calling DAL operations and writes ownership tuples
  after successful registration. The `owner` field on Resource is
  informational.
- **Annotation ingestion is downstream.** Section A/B/C fields mirror the
  biomodel-annotator *annotation package* (value/source/confidence + ontology
  IRIs), but the DAL stores **values only** and takes no YAML dependency.
  Parsing an annotation package into a `Resource` belongs to the discovery
  API, not this layer. `scripts/align_annotation.py` is a non-packaged
  reference probe showing that mapping, not library API.

### What this layer is not

Not in scope, by design:

| Concern | Owner |
|---|---|
| HTTP API | Discovery Gateway (`model-discovery/api`) |
| UI | Separate frontend project |
| Execution orchestration (job submission, status polling) | HeLx integration layer |
| Data movement / replication | iRODS |
| Advanced search (fuzzy, ranking, faceted) | Search Service (Elasticsearch) |
| Vocabulary governance / curation | Community process |
| OpenFGA tuple management | Service layer |

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

For a consumer-facing API reference (import surface, Resource fields, value
types, operations, gotchas) — see **[docs/library-usage.md](docs/library-usage.md)**.

For a longer walkthrough — full end-to-end pipeline, lineage tracing
patterns, testing recipes — see **[docs/guide.md](docs/guide.md)**.

For the architectural spec (design principles, FAIR mapping, OpenFGA model,
iRODS architecture, upgrade paths), see **[docs/spec.md](docs/spec.md)** if
present, or the design document this README accompanies.

---

## TODO / Roadmap

Items below are **specified in the design doc but not yet implemented**, plus
forward-looking work surfaced during the most recent review. Keep this list
honest — move items out of TODO as they ship.

### Schema fields specified but not yet shipped

- [ ] **`pid` field** — persistent identifier (DOI, ARK, Handle). Today
      cross-refs go through `external_ids["doi"]`. Promote to a first-class
      field once a minting service exists.
- [ ] **`doi` auto-generation** on registration — design doc shows `doi`
      flowing from DataCite. No DOI minting integration today; `external_ids`
      is the workaround.
- [x] **`infectiousAgent` / `species`** — resolved. `organisms` holds
      `biology.species`; `infectious_agents` is a distinct snake_case field
      (schema.md alignment). Value-only labels; ontology IRIs not stored yet.
- [ ] **Tag normalization for non-`format_tags` arrays** — `organisms`,
      `model_scales`, `domains` are stored as-given. Lowercase / strip
      / dedupe to match `format_tags` semantics, **or** explicitly document
      that they're proper-case (e.g. `SARS-CoV-2`, `Homo sapiens`).

### iRODS integration (specified, not implemented)

The design doc Section 5 describes a two-store model. Today only Postgres is
wired up. The following are **not yet shipped**:

- [ ] **AVU projection** on registration — `mism:registry_id`, `mism:name`,
      `mism:resource_type`, `mism:version`, `mism:organism` (one per),
      `mism:scale` (one per), `mism:license`, `mism:format` (one per),
      `mism:doi`, `mism:status`. Currently `register_*` only writes to
      Postgres.
- [ ] **iRODS ACL sync** — set initial ACLs on resource creation
      (`owner` → own, consortium group → read).
- [ ] **iRODS-computed `digest_sha256` + `size_bytes` autopopulation** —
      design says these fill automatically on ingest. Today they have to be
      passed explicitly.
- [ ] **AVU drift reconciliation job** — Postgres is source of truth; a
      periodic checker should detect AVUs edited directly in iRODS and
      restore them. Operational procedure for now.
- [ ] **Recommended iRODS rules** — on-ingest registry-id check,
      post-ingest checksum notify, replication-verify metadata. These are
      separate iRODS rule files, not library code.

### Authorization (specified, not implemented)

- [ ] **OpenFGA model** — `platform` + `artifact` types with `executor`,
      `owner`, `viewer` relations and the derived `can_view`, `can_download`,
      `can_update`, `can_delete`, `can_archive`, `can_add_owner`,
      `can_remove_owner`, `can_remove_self_as_owner` permissions. Not
      configured anywhere yet.
- [ ] **Service-layer authz hooks** — Discovery Gateway has `# FUTURE: fga.*`
      placeholders but no real OpenFGA client.

### Operations / API surface

- [ ] **`search_resources` on `InMemoryRegistry`** — currently only
      `PostgresRegistry` implements it. A naive in-memory implementation
      (substring + filter, no ranking) would let tests exercise the search
      path without spinning up Postgres.
- [ ] **Run groups / Workflow Run** — lightweight umbrella that groups
      multiple `Run`s. Currently a multi-stage pipeline is just an implicit
      chain through input/output IDs.
- [ ] **Reproducibility score** — computed boolean/score on `Run` flagging
      whether enough metadata is present (digest? container? parameters?
      seed?) to reproduce.
- [ ] **IOSpec inference from run history** — after N successful runs,
      suggest an `IOSpec` based on the common tags of inputs/outputs.

### Upgrade paths (no schema impact)

These show up in the design doc Section 9. Tracking here so they don't get
lost:

- [ ] **CEDAR template integration** for ontology-backed registration UI.
- [ ] **Tag → ontology URI mapping table** + `resolve_tag()` helper.
- [ ] **Croissant export** for ML datasets.
- [ ] **Model Cards export** for models.
- [ ] **PROV-O / RO-Crate export** for provenance graphs.
- [ ] **BCO export** for biological compute objects.
- [ ] **LinkML schema generation** from the dataclasses.
- [ ] **Graph DB read-projection** (Neo4j / Neptune) for deep lineage queries.

### Testing / quality

- [ ] **Property-based tests** for tag normalization (hypothesis).
- [ ] **Migration round-trip test** — apply all migrations against a
      throwaway Postgres, register every entity, dump + restore, verify
      equality.
- [ ] **Backend conformance suite** — run the same operation tests against
      `InMemoryRegistry` and `PostgresRegistry` to catch divergence.

### Spec-review notes (issues found in the design document during this rewrite)

These are corrections / inconsistencies to fix in the **design doc itself**,
not in code:

- The Resource field tier table shows `model_scales` with a duplicated
  phrase: `"recommended for resource_type=dataset, recommended for
  resource_type=dataset"`. Drop one and decide what's required vs.
  recommended for the model case.
- `infectiousAgent` is listed in camelCase while every other field in the
  schema is snake_case. Pick a convention.
- The doc states `register_dataset` and `register_model` "also write the AVU
  projection to iRODS and set initial iRODS ACLs (see Section 5)". Today
  they don't — either implement this or soften the language to "intended
  to write the AVU projection (not yet implemented; see TODO)".
- The doc says `digest_sha256` is "populated automatically on ingest" for
  iRODS-stored data. Same situation — this is aspirational, not current.
- Open Question #2 (multi-file resources) is unresolved. Worth deciding
  before too many heterogeneous resources accumulate. Candidate answer:
  `location_uri` may point at a directory / iRODS collection; the file
  enumeration is the access layer's responsibility.
- Section 4.1 says `register_*` "Validation: name and location_uri required"
  but Section 3.1 lists `description` as required. Reconcile.
- `find_resources` parameter list in Section 7.1 omits `domains`,
  `name_contains`, `version_status`, `date_published_after`,
  `date_published_before`, which the Protocol now accepts.

## License

MIT
