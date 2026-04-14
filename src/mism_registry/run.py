"""Run entity — records model execution."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Any

from .enums import RunStatus
from .types import RunEnvironment


@dataclasses.dataclass(slots=True, kw_only=True)
class Run:
    """Records a single execution of a model with specific inputs."""

    # Identity
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))

    # Required references
    model_id: str
    status: RunStatus = RunStatus.REGISTERED

    # Denormalized for reproducibility
    model_version: str = ""

    # Input/output resource IDs
    input_resource_ids: list[str] = dataclasses.field(default_factory=list)
    output_resource_ids: list[str] = dataclasses.field(default_factory=list)

    # Execution details
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    environment: RunEnvironment | None = None

    # Lifecycle
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str = ""
    log_uri: str = ""
    triggered_by: str = ""
    notes: str = ""

    # Auto timestamp
    created_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc))
