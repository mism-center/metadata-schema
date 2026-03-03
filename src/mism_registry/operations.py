"""Public high-level API functions for the MISM registry."""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import Any

from .enums import ExecutionType, ResourceType, RunStatus
from .errors import ValidationError
from .protocol import Registry
from .resource import Resource
from .run import Run
from .types import IOSpec, RunEnvironment
from .validation import (
    check_iospec_handshake,
    validate_execution_fields,
    validate_resource_required_fields,
    validate_run_status_transition,
)

# ── Registration ──────────────────────────────────────────────────────


def register_dataset(
    registry: Registry,
    *,
    name: str,
    location_uri: str,
    description: str = "",
    version: str = "",
    format_tags: list[str] | None = None,
    digest_sha256: str = "",
    size_bytes: int | None = None,
    external_ids: dict[str, str] | None = None,
    license: str = "",
    owner: str = "",
    metadata: dict[str, Any] | None = None,
) -> Resource:
    """Register a dataset resource."""
    resource = Resource(
        name=name,
        resource_type=ResourceType.DATASET,
        location_uri=location_uri,
        description=description,
        version=version,
        format_tags=format_tags or [],
        digest_sha256=digest_sha256,
        size_bytes=size_bytes,
        external_ids=external_ids or {},
        license=license,
        owner=owner,
        metadata=metadata or {},
    )
    validate_resource_required_fields(resource)
    return registry.register_resource(resource)


def register_model(
    registry: Registry,
    *,
    name: str,
    location_uri: str,
    execution_type: ExecutionType,
    description: str = "",
    version: str = "",
    format_tags: list[str] | None = None,
    digest_sha256: str = "",
    size_bytes: int | None = None,
    execution_ref: str = "",
    io_spec: IOSpec | None = None,
    external_ids: dict[str, str] | None = None,
    license: str = "",
    owner: str = "",
    metadata: dict[str, Any] | None = None,
    resource_type: ResourceType = ResourceType.MODEL,
) -> Resource:
    """Register a model or tool resource."""
    if resource_type not in (ResourceType.MODEL, ResourceType.TOOL):
        raise ValidationError("register_model only accepts MODEL or TOOL resource types")
    resource = Resource(
        name=name,
        resource_type=resource_type,
        location_uri=location_uri,
        execution_type=execution_type,
        execution_ref=execution_ref,
        io_spec=io_spec,
        description=description,
        version=version,
        format_tags=format_tags or [],
        digest_sha256=digest_sha256,
        size_bytes=size_bytes,
        external_ids=external_ids or {},
        license=license,
        owner=owner,
        metadata=metadata or {},
    )
    validate_resource_required_fields(resource)
    validate_execution_fields(resource)
    return registry.register_resource(resource)


# ── Execution tracking ────────────────────────────────────────────────


def prepare_run(
    registry: Registry,
    *,
    model_id: str,
    input_resource_ids: list[str],
    parameters: dict[str, Any] | None = None,
    environment: RunEnvironment | None = None,
    triggered_by: str = "",
    notes: str = "",
) -> Run:
    """Create a Run in REGISTERED status.

    Validates model exists, inputs exist, and performs IOSpec handshake if available.
    """
    model = registry.get_resource(model_id)
    if model.resource_type not in (ResourceType.MODEL, ResourceType.TOOL):
        raise ValidationError(
            f"Resource '{model_id}' is a {model.resource_type.value}, not a model or tool"
        )

    input_resources = []
    for rid in input_resource_ids:
        input_resources.append(registry.get_resource(rid))

    if model.io_spec is not None:
        check_iospec_handshake(model.io_spec, input_resources)
    elif input_resource_ids:
        warnings.warn(
            f"Model '{model.name}' has no io_spec — skipping input compatibility check.",
            UserWarning,
            stacklevel=2,
        )

    run = Run(
        model_id=model_id,
        model_version=model.version,
        input_resource_ids=list(input_resource_ids),
        parameters=parameters or {},
        environment=environment,
        status=RunStatus.REGISTERED,
        triggered_by=triggered_by,
        notes=notes,
    )
    return registry.create_run(run)


def start_run(
    registry: Registry,
    *,
    run_id: str,
) -> Run:
    """Transition a run from REGISTERED to RUNNING."""
    run = registry.get_run(run_id)
    validate_run_status_transition(run.status, RunStatus.RUNNING)
    run.status = RunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    return registry.update_run(run)


def complete_run(
    registry: Registry,
    *,
    run_id: str,
    output_resources: list[Resource],
) -> Run:
    """Mark a run as completed and register its output resources."""
    run = registry.get_run(run_id)
    validate_run_status_transition(run.status, RunStatus.COMPLETED)

    registered_outputs = []
    for res in output_resources:
        validate_resource_required_fields(res)
        registered = registry.register_resource(res)
        registered_outputs.append(registered)

    run.status = RunStatus.COMPLETED
    run.output_resource_ids = [r.id for r in registered_outputs]
    run.completed_at = datetime.now(timezone.utc)
    return registry.update_run(run)


def fail_run(
    registry: Registry,
    *,
    run_id: str,
    error_message: str = "",
    log_uri: str = "",
) -> Run:
    """Mark a run as failed with optional error details."""
    run = registry.get_run(run_id)
    validate_run_status_transition(run.status, RunStatus.FAILED)
    run.status = RunStatus.FAILED
    run.error_message = error_message
    run.log_uri = log_uri
    run.completed_at = datetime.now(timezone.utc)
    return registry.update_run(run)


def cancel_run(
    registry: Registry,
    *,
    run_id: str,
) -> Run:
    """Cancel a run from REGISTERED or RUNNING state."""
    run = registry.get_run(run_id)
    validate_run_status_transition(run.status, RunStatus.CANCELLED)
    run.status = RunStatus.CANCELLED
    run.completed_at = datetime.now(timezone.utc)
    return registry.update_run(run)


# ── Discovery (thin delegation) ──────────────────────────────────────


def find_resources(
    registry: Registry,
    *,
    resource_type: ResourceType | None = None,
    tags: list[str] | None = None,
    owner: str | None = None,
    name_contains: str | None = None,
) -> list[Resource]:
    """Search resources by type, tags, owner, or name substring."""
    return registry.find_resources(
        resource_type=resource_type,
        tags=tags,
        owner=owner,
        name_contains=name_contains,
    )


def find_runs(
    registry: Registry,
    *,
    model_id: str | None = None,
    input_resource_id: str | None = None,
    status: RunStatus | None = None,
) -> list[Run]:
    """Search runs by model, input resource, or status."""
    return registry.find_runs(
        model_id=model_id,
        input_resource_id=input_resource_id,
        status=status,
    )


def get_lineage(registry: Registry, resource_id: str) -> list[Run]:
    """Trace backwards: what runs produced this resource?"""
    return registry.get_lineage(resource_id)


def get_dependents(registry: Registry, resource_id: str) -> list[Run]:
    """Trace forwards: what runs used this resource as input?"""
    return registry.get_dependents(resource_id)
