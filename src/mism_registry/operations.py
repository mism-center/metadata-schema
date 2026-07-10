"""Public high-level API functions for the MISM registry."""

from __future__ import annotations

import warnings
from datetime import date, datetime, timezone
from typing import Any

from .enums import (
    ExecutionType,
    ResourceRegistrationStatus,
    ResourceType,
    ResourceVersionStatus,
    RunStatus,
)
from .errors import ValidationError
from .protocol import Registry
from .resource import Resource
from .run import Run
from .run_detail import ModelRunSummary
from .types import Author, IOSpec, Publication, RunEnvironment
from .validation import (
    check_iospec_handshake,
    validate_execution_fields,
    validate_registration_approved,
    validate_registration_status_transition,
    validate_resource_is_active,
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
    # Authorship & attribution
    authors: list[Author] | None = None,
    organization: str = "",
    contact_email: str = "",
    publications: list[Publication] | None = None,
    funding: list[str] | None = None,
    # Scientific context
    model_scales: list[str] | None = None,
    organisms: list[str] | None = None,
    domains: list[str] | None = None,
    date_published: date | None = None,
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
        authors=authors or [],
        organization=organization,
        contact_email=contact_email,
        publications=publications or [],
        funding=funding or [],
        model_scales=model_scales or [],
        organisms=organisms or [],
        domains=domains or [],
        date_published=date_published,
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
    # Authorship & attribution
    authors: list[Author] | None = None,
    organization: str = "",
    contact_email: str = "",
    publications: list[Publication] | None = None,
    funding: list[str] | None = None,
    # Scientific context
    model_scales: list[str] | None = None,
    organisms: list[str] | None = None,
    domains: list[str] | None = None,
    date_published: date | None = None,
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
        authors=authors or [],
        organization=organization,
        contact_email=contact_email,
        publications=publications or [],
        funding=funding or [],
        model_scales=model_scales or [],
        organisms=organisms or [],
        domains=domains or [],
        date_published=date_published,
    )
    validate_resource_required_fields(resource)
    validate_execution_fields(resource)
    return registry.register_resource(resource)


# ── Versioning ────────────────────────────────────────────────────────


def create_new_version(
    registry: Registry,
    *,
    original_id: str,
    location_uri: str,
    version: str = "",
    digest_sha256: str = "",
    size_bytes: int | None = None,
    description: str | None = None,
    format_tags: list[str] | None = None,
    io_spec: IOSpec | None = None,
    metadata: dict[str, Any] | None = None,
    owner: str = "",
) -> Resource:
    """Create a new version of an existing resource.

    The original is marked as superseded. The new resource gets a new UUID
    and a new_version_of pointer back to the original.
    """
    original = registry.get_resource(original_id)
    validate_resource_is_active(original)

    new_resource = Resource(
        name=original.name,
        resource_type=original.resource_type,
        location_uri=location_uri,
        description=description if description is not None else original.description,
        version=version or original.version,
        format_tags=format_tags if format_tags is not None else list(original.format_tags),
        digest_sha256=digest_sha256,
        size_bytes=size_bytes,
        execution_type=original.execution_type,
        execution_ref=original.execution_ref,
        io_spec=io_spec if io_spec is not None else original.io_spec,
        external_ids=dict(original.external_ids),
        license=original.license,
        owner=owner or original.owner,
        metadata=metadata if metadata is not None else dict(original.metadata),
        new_version_of=original.id,
        # Carry forward authorship and scientific context
        authors=list(original.authors),
        organization=original.organization,
        contact_email=original.contact_email,
        publications=list(original.publications),
        funding=list(original.funding),
        model_scales=list(original.model_scales),
        organisms=list(original.organisms),
        domains=list(original.domains),
        date_published=original.date_published,
    )
    validate_resource_required_fields(new_resource)

    registered = registry.register_resource(new_resource)

    # Mark original as superseded
    original.version_status = ResourceVersionStatus.SUPERSEDED
    original.superseded_by = registered.id
    original.updated_at = datetime.now(timezone.utc)
    registry.update_resource(original)

    return registered


# ── Registration workflow ─────────────────────────────────────────────


def set_registration_status(
    registry: Registry,
    *,
    resource_id: str,
    target: ResourceRegistrationStatus,
) -> Resource:
    """Advance a resource through the registration workflow.

    Validates the transition against the legal state machine
    (draft -> annotating -> pending_review -> approved, with failure/reject
    branches) before persisting. Raises InvalidStateTransitionError on an
    illegal move.
    """
    resource = registry.get_resource(resource_id)
    validate_registration_status_transition(resource.registration_status, target)
    resource.registration_status = target
    resource.updated_at = datetime.now(timezone.utc)
    return registry.update_resource(resource)


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

    Validates model exists and is active, inputs exist and are active,
    and performs IOSpec handshake if available.
    """
    model = registry.get_resource(model_id)
    if model.resource_type not in (ResourceType.MODEL, ResourceType.TOOL):
        raise ValidationError(
            f"Resource '{model_id}' is a {model.resource_type.value}, not a model or tool"
        )
    validate_resource_is_active(model)
    # Registration gate: only approved models are executable.
    validate_registration_approved(model)

    input_resources = []
    for rid in input_resource_ids:
        r = registry.get_resource(rid)
        validate_resource_is_active(r)
        input_resources.append(r)

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
    organisms: list[str] | None = None,
    scales: list[str] | None = None,
) -> list[Resource]:
    """Search resources by type, tags, owner, name substring, organisms, or scales."""
    return registry.find_resources(
        resource_type=resource_type,
        tags=tags,
        owner=owner,
        name_contains=name_contains,
        organisms=organisms,
        scales=scales,
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


def get_model_run_details(
    registry: Registry,
    *,
    model_id: str,
    status: RunStatus | None = None,
) -> ModelRunSummary:
    """Fetch all runs for a model, enriched with full Resource details.

    Returns the model Resource and a list of ModelRunDetail objects, each
    containing the Run plus hydrated input and output Resources.  Designed
    to populate a "Model Runs" page in a single call.

    Args:
        registry: The registry backend to query.
        model_id: ID of a MODEL or TOOL resource.
        status: Optional filter — only include runs with this status.

    Raises:
        ResourceNotFoundError: If *model_id* does not exist.
        ValidationError: If *model_id* does not point to a MODEL or TOOL.
    """
    # Validate the model is a MODEL or TOOL before delegating to the backend
    model = registry.get_resource(model_id)
    if model.resource_type not in (ResourceType.MODEL, ResourceType.TOOL):
        raise ValidationError(
            f"Resource '{model_id}' is a {model.resource_type.value}, not a model or tool"
        )

    return registry.get_model_run_details(model_id, status=status)


def get_latest_version(registry: Registry, resource_id: str) -> Resource | None:
    """Follow the version chain forward to the current active version."""
    return registry.get_latest_version(resource_id)


def get_version_history(registry: Registry, resource_id: str) -> list[Resource]:
    """Return the full version chain for a resource, oldest first."""
    return registry.get_version_history(resource_id)
