"""Validation helpers: field checks, tag normalization, IOSpec handshake, state machine."""

from __future__ import annotations

import warnings

from .enums import ResourceStatus, ResourceType, RunStatus
from .errors import (
    InvalidStateTransitionError,
    IOSpecMismatchError,
    ValidationError,
)
from .resource import Resource
from .types import IOSpec


def validate_resource_required_fields(resource: Resource) -> None:
    """Ensure name and location_uri are non-empty."""
    if not resource.name.strip():
        raise ValidationError("Resource name must be non-empty")
    if not resource.location_uri.strip():
        raise ValidationError("Resource location_uri must be non-empty")


def validate_execution_fields(resource: Resource) -> None:
    """For model/tool: execution_type must be set. Warn if io_spec is absent."""
    if resource.resource_type in (ResourceType.MODEL, ResourceType.TOOL):
        if resource.execution_type is None:
            raise ValidationError(
                f"execution_type is required for resource_type={resource.resource_type.value}"
            )
        if resource.io_spec is None:
            warnings.warn(
                f"Resource '{resource.name}' is a {resource.resource_type.value} "
                f"but has no io_spec. Consider defining inputs/outputs.",
                UserWarning,
                stacklevel=3,
            )


def validate_resource_is_active(resource: Resource) -> None:
    """Ensure a resource is in ACTIVE status for operations that require it."""
    if resource.status != ResourceStatus.ACTIVE:
        raise ValidationError(
            f"Resource '{resource.id}' has status '{resource.status.value}', expected 'active'"
        )


def normalize_tags(tags: list[str]) -> list[str]:
    """Lowercase, strip, deduplicate, sort."""
    return sorted(set(t.lower().strip() for t in tags if t.strip()))


def check_iospec_handshake(
    io_spec: IOSpec,
    input_resources: list[Resource],
) -> None:
    """Validate that input resources satisfy the IOSpec's required input slots.

    For each required input slot, at least one input resource must have
    format_tags that are a superset of the slot's tags.
    """
    for slot in io_spec.inputs:
        if not slot.required:
            continue
        slot_tags = set(slot.tags)
        if not slot_tags:
            continue
        matched = any(slot_tags.issubset(set(r.format_tags)) for r in input_resources)
        if not matched:
            raise IOSpecMismatchError(
                f"No input resource satisfies slot '{slot.name}' "
                f"(requires tags: {list(slot.tags)})"
            )


# Legal state transitions for RunStatus
_VALID_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.REGISTERED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}


def validate_run_status_transition(current: RunStatus, target: RunStatus) -> None:
    """Raise InvalidStateTransitionError if the transition is illegal."""
    if target not in _VALID_TRANSITIONS.get(current, set()):
        raise InvalidStateTransitionError(
            f"Cannot transition run from {current.value} to {target.value}"
        )
