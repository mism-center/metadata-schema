"""Resource entity — the central registry object."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime, timezone
from typing import Any

from .enums import ExecutionType, ResourceStatus, ResourceType
from .types import Author, IOSpec, Publication


@dataclasses.dataclass(slots=True, kw_only=True)
class Resource:
    """A registered dataset, model, or tool."""

    # Identity & description
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    resource_type: ResourceType
    location_uri: str
    description: str = ""
    version: str = ""
    status: ResourceStatus = ResourceStatus.ACTIVE
    new_version_of: str = ""
    superseded_by: str = ""

    # Authorship & attribution
    authors: list[Author] = dataclasses.field(default_factory=list)
    organization: str = ""
    contact_email: str = ""
    publications: list[Publication] = dataclasses.field(default_factory=list)
    funding: list[str] = dataclasses.field(default_factory=list)

    # Scientific context
    modeling_scales: list[str] = dataclasses.field(default_factory=list)
    organisms: list[str] = dataclasses.field(default_factory=list)
    domains: list[str] = dataclasses.field(default_factory=list)
    date_published: date | None = None

    # Location & integrity
    format_tags: list[str] = dataclasses.field(default_factory=list)
    digest_sha256: str = ""
    size_bytes: int | None = None
    external_ids: dict[str, str] = dataclasses.field(default_factory=dict)
    license: str = ""

    # Execution-related (conditional: required for model/tool)
    execution_type: ExecutionType | None = None
    execution_ref: str = ""
    io_spec: IOSpec | None = None

    # System
    owner: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    created_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        # Normalize format_tags: lowercase, strip, deduplicate, sort
        self.format_tags = sorted(set(t.lower().strip() for t in self.format_tags if t.strip()))
