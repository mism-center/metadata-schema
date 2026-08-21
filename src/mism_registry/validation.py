"""Validation helpers: field checks, tag normalization, IOSpec handshake, state machine."""

from __future__ import annotations

import warnings

from .enums import (
    ImageReviewStatus,
    ResourceRegistrationStatus,
    ResourceType,
    ResourceVersionStatus,
    RunStatus,
)
from .errors import (
    InvalidStateTransitionError,
    IOSpecMismatchError,
    ValidationError,
)
from .resource import Resource
from .types import EntryPoint, IOSpec


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
    """Ensure a resource is in ACTIVE version status for operations that require it."""
    if resource.version_status != ResourceVersionStatus.ACTIVE:
        raise ValidationError(
            f"Resource '{resource.id}' has version_status "
            f"'{resource.version_status.value}', expected 'active'"
        )


def validate_registration_approved(resource: Resource) -> None:
    """Ensure a resource's registration workflow reached APPROVED before use."""
    if resource.registration_status != ResourceRegistrationStatus.APPROVED:
        raise ValidationError(
            f"Resource '{resource.id}' has registration_status "
            f"'{resource.registration_status.value}', expected 'approved'. "
            f"Complete metadata review and approval before running."
        )


def validate_image_approved_if_shipped(resource: Resource) -> None:
    """If a resource ships a Container recipe, its image must be approved before use."""
    if resource.containers and resource.image_review_status != ImageReviewStatus.IMAGE_APPROVED:
        raise ValidationError(
            f"Resource '{resource.id}' ships a container recipe but has image_review_status "
            f"'{resource.image_review_status.value}', expected 'image_approved'. "
            f"Complete Dockerfile/image review before running."
        )


def validate_run_arguments(entry_point: EntryPoint, arguments: dict[str, object]) -> None:
    """Validate caller-supplied argument values against an entry point's
    declared Arguments. Injection defense: the caller supplies only VALUES
    keyed by declared arg names — never command/flag strings.

    Rejects unknown names, enforces enum membership, requires every
    positional argument to have a value (supplied or via a non-null default).
    """
    by_name = {a.name: a for a in entry_point.arguments}
    for name in arguments:
        if name not in by_name:
            raise ValidationError(
                f"Unknown argument '{name}' for entry point '{entry_point.command}'"
            )
    for arg in entry_point.arguments:
        supplied = arg.name in arguments
        value = arguments[arg.name] if supplied else arg.default
        if arg.enums is not None and value is not None and value not in arg.enums:
            raise ValidationError(
                f"Argument '{arg.name}'={value!r} not in allowed values {arg.enums}"
            )
        # Positional args (position > 0) must resolve to a value.
        if arg.position and value is None:
            raise ValidationError(f"Positional argument '{arg.name}' requires a value")


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


# Legal state transitions for the registration workflow.
_R = ResourceRegistrationStatus
_VALID_REGISTRATION_TRANSITIONS: dict[
    ResourceRegistrationStatus, set[ResourceRegistrationStatus]
] = {
    _R.DRAFT: {_R.ANNOTATING},
    _R.ANNOTATING: {_R.PENDING_REVIEW, _R.ANNOTATION_FAILED},
    _R.ANNOTATION_FAILED: {_R.ANNOTATING},  # retry the agent job
    _R.PENDING_REVIEW: {_R.APPROVED, _R.REJECTED, _R.ANNOTATING},
    _R.REJECTED: {_R.ANNOTATING, _R.PENDING_REVIEW},  # regenerate, or resubmit after manual fix
    _R.APPROVED: set(),  # terminal
}


def validate_registration_status_transition(
    current: ResourceRegistrationStatus,
    target: ResourceRegistrationStatus,
) -> None:
    """Raise InvalidStateTransitionError if the registration transition is illegal."""
    if target not in _VALID_REGISTRATION_TRANSITIONS.get(current, set()):
        raise InvalidStateTransitionError(
            f"Cannot transition registration from {current.value} to {target.value}"
        )


# Legal state transitions for the Dockerfile/image review workflow (MISM-291).
_I = ImageReviewStatus
_VALID_IMAGE_REVIEW_TRANSITIONS: dict[ImageReviewStatus, set[ImageReviewStatus]] = {
    _I.NOT_APPLICABLE: {_I.PENDING_IMAGE_CHECK},
    _I.PENDING_IMAGE_CHECK: {_I.IMAGE_APPROVED, _I.IMAGE_REJECTED},
    _I.IMAGE_APPROVED: {_I.PENDING_IMAGE_CHECK},  # resubmitting a replacement image
    _I.IMAGE_REJECTED: {_I.PENDING_IMAGE_CHECK},  # manual resubmission only — no auto bounceback
}


def validate_image_review_status_transition(
    current: ImageReviewStatus,
    target: ImageReviewStatus,
) -> None:
    """Raise InvalidStateTransitionError if the image-review transition is illegal."""
    if target not in _VALID_IMAGE_REVIEW_TRANSITIONS.get(current, set()):
        raise InvalidStateTransitionError(
            f"Cannot transition image_review_status from {current.value} to {target.value}"
        )
