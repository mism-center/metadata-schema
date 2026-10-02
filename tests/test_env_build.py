"""Tests for the agent environment-build status workflow."""

import pytest

from mism_registry import (
    EnvBuildStatus,
    ExecutionType,
    InMemoryRegistry,
    InvalidStateTransitionError,
    Resource,
    ResourceRegistrationStatus,
    ResourceType,
    ValidationError,
    prepare_run,
    set_env_build_status,
    set_registration_status,
)
from mism_registry.validation import validate_env_build_status_transition

_E = EnvBuildStatus
_R = ResourceRegistrationStatus


def test_default_not_ready():
    r = Resource(name="m", resource_type=ResourceType.MODEL, location_uri="s3://x")
    assert r.env_build_status == _E.NOT_READY
    assert r.env_build_error == ""


def _approved_model(registry: InMemoryRegistry) -> Resource:
    """Draft model walked to APPROVED only (env not built)."""
    m = registry.register_resource(
        Resource(
            name="m",
            resource_type=ResourceType.MODEL,
            location_uri="s3://x",
            execution_type=ExecutionType.PYTHON,
        )
    )
    for target in (_R.ANNOTATING, _R.PENDING_REVIEW, _R.APPROVED):
        m = set_registration_status(registry, resource_id=m.id, target=target)
    return m


def test_approval_queues_build(registry: InMemoryRegistry):
    assert _approved_model(registry).env_build_status == _E.READY_FOR_BUILD


def test_happy_path_and_failure_retry(registry: InMemoryRegistry):
    m = _approved_model(registry)
    m = set_env_build_status(registry, resource_id=m.id, target=_E.BUILDING)
    m = set_env_build_status(registry, resource_id=m.id, target=_E.BUILD_FAILED, error="pip boom")
    assert m.env_build_error == "pip boom"
    m = set_env_build_status(registry, resource_id=m.id, target=_E.READY_FOR_BUILD)
    m = set_env_build_status(registry, resource_id=m.id, target=_E.BUILDING)
    m = set_env_build_status(registry, resource_id=m.id, target=_E.RUNNABLE)
    assert m.env_build_status == _E.RUNNABLE
    assert m.env_build_error == ""


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (_E.NOT_READY, _E.RUNNABLE),
        (_E.READY_FOR_BUILD, _E.RUNNABLE),
        (_E.BUILDING, _E.READY_FOR_BUILD),
        (_E.BUILD_FAILED, _E.RUNNABLE),
    ],
)
def test_illegal_transitions(current, target):
    with pytest.raises(InvalidStateTransitionError):
        validate_env_build_status_transition(current, target)


def test_prepare_run_requires_runnable_env(registry: InMemoryRegistry, sample_model):
    # sample_model is built (RUNNABLE); queue a rebuild -> no longer executable.
    set_env_build_status(registry, resource_id=sample_model.id, target=_E.READY_FOR_BUILD)
    with pytest.raises(ValidationError, match="runnable"):
        prepare_run(registry, model_id=sample_model.id, input_resource_ids=[])
