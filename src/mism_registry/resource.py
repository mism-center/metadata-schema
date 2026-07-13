"""Resource entity — the central registry object."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from typing import Any

from .enums import (
    ExecutionType,
    ResourceRegistrationStatus,
    ResourceType,
    ResourceVersionStatus,
)
from .types import (
    Author,
    Compute,
    Contact,
    Container,
    Dependency,
    EntryPoint,
    IODetail,
    IOSpec,
    Publication,
    RelatedResource,
    TestSpec,
)


@dataclasses.dataclass(slots=True, kw_only=True)
class Resource:
    """A registered dataset, model, or tool."""

    # Identity & description
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    resource_type: ResourceType
    location_uri: str
    short_description: str = ""  # schema.md model.short_description
    description: str = ""  # maps to schema.md model.long_description
    version: str = ""
    # Version lifecycle (is this the current version?)
    version_status: ResourceVersionStatus = ResourceVersionStatus.ACTIVE
    # Registration workflow (upload -> annotate -> review -> approve).
    # Defaults to DRAFT; workflow promotes through annotating -> review -> approve.
    registration_status: ResourceRegistrationStatus = ResourceRegistrationStatus.DRAFT
    new_version_of: str = ""
    superseded_by: str = ""

    # Authorship & attribution
    authors: list[Author] = dataclasses.field(default_factory=list)
    contacts: list[Contact] = dataclasses.field(default_factory=list)
    organization: str = ""
    contact_email: str = ""
    publications: list[Publication] = dataclasses.field(default_factory=list)
    related_resources: list[RelatedResource] = dataclasses.field(default_factory=list)
    funding: list[str] = dataclasses.field(default_factory=list)  # ponytail: typed Funding later

    # Scientific context
    model_scales: list[str] = dataclasses.field(default_factory=list)
    organisms: list[str] = dataclasses.field(default_factory=list)  # schema biology.species
    domains: list[str] = dataclasses.field(default_factory=list)  # schema biology.topic_category
    date_published: date | None = None

    # Model characterization (schema.md Section A, values only)
    model_class: list[str] = dataclasses.field(default_factory=list)  # MAMO labels
    formalism: list[str] = dataclasses.field(default_factory=list)  # MAMO/KISAO labels
    determinism: str = "unknown"  # deterministic | stochastic | hybrid | unknown
    time_dynamics: str = "unknown"  # continuous | discrete | event-driven | static | unknown
    spatial: str = "unknown"  # non-spatial | well-mixed | 1D | 2D | 3D | lattice | ...
    multiscale: bool | None = None

    # Biology (schema.md model.biology, values only)
    infectious_agents: list[str] = dataclasses.field(default_factory=list)
    health_conditions: list[str] = dataclasses.field(default_factory=list)
    biological_processes: list[str] = dataclasses.field(default_factory=list)
    molecular_entities: list[str] = dataclasses.field(default_factory=list)
    proteins_genes: list[str] = dataclasses.field(default_factory=list)

    # Location & integrity
    format_tags: list[str] = dataclasses.field(default_factory=list)
    digest_sha256: str = ""
    size_bytes: int | None = None
    external_ids: dict[str, str] = dataclasses.field(default_factory=dict)
    license: str = ""

    # Execution-related (conditional: required for model/tool)
    execution_type: ExecutionType | None = None  # schema.md execution.environment_kind
    execution_ref: str = ""
    io_spec: IOSpec | None = None  # drives the run-time input handshake

    # Execution characterization (schema.md Section B, values only)
    execution_status: str = ""  # characterized | partially_characterized | not_determined
    language_name: str = ""
    language_version: str = ""
    execution_notes: str = ""
    dependencies: list[Dependency] = dataclasses.field(default_factory=list)
    containers: list[Container] = dataclasses.field(default_factory=list)
    compute: Compute | None = None
    entry_points: list[EntryPoint] = dataclasses.field(default_factory=list)
    tests: TestSpec | None = None

    # Rich I/O characterization (schema.md Section C)
    io: IODetail | None = None

    # System
    owner: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    created_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        # Normalize format_tags: lowercase, strip, deduplicate, sort
        self.format_tags = sorted(set(t.lower().strip() for t in self.format_tags if t.strip()))
