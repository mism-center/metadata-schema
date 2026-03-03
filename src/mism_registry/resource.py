"""Resource entity — the central registry object."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Any

from .enums import ExecutionType, ResourceType
from .types import IOSpec


@dataclasses.dataclass(slots=True, kw_only=True)
class Resource:
    """A registered dataset, model, or tool."""

    # Identity
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))

    # Required fields
    name: str
    resource_type: ResourceType
    location_uri: str

    # Optional descriptive fields
    description: str = ""
    version: str = ""
    format_tags: list[str] = dataclasses.field(default_factory=list)
    digest_sha256: str = ""
    size_bytes: int | None = None

    # Execution-related (conditional: required for model/tool)
    execution_type: ExecutionType | None = None
    execution_ref: str = ""
    io_spec: IOSpec | None = None

    # Extensibility
    external_ids: dict[str, str] = dataclasses.field(default_factory=dict)
    license: str = ""
    owner: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    # Timestamps (auto-managed)
    created_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        # Normalize format_tags: lowercase, strip, deduplicate, sort
        self.format_tags = sorted(set(t.lower().strip() for t in self.format_tags if t.strip()))
