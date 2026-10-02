"""Tests for the agent environment-build status workflow."""

import pytest

from mism_registry import (
    EnvBuildStatus,
    InMemoryRegistry,
    InvalidStateTransitionError,
    Resource,
    ResourceType,
    set_env_build_status,
)
from mism_registry.validation import validate_env_build_status_transition

_E = EnvBuildStatus


def test_default_not_ready():
    r = Resource(name="m", resource_type=ResourceType.MODEL, location_uri="s3://x")
    assert r.env_build_status == _E.NOT_READY
    assert r.env_build_error == ""


def test_approval_queues_build(sample_model):
    # sample_model fixture is approved via set_registration_status
    assert sample_model.env_build_status == _E.READY_FOR_BUILD


def test_happy_path_and_failure_retry(registry: InMemoryRegistry, sample_model):
    m = set_env_build_status(registry, resource_id=sample_model.id, target=_E.BUILDING)
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
