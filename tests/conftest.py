"""Shared test fixtures."""

import pytest

from mism_registry import (
    ExecutionType,
    InMemoryRegistry,
    IOSlot,
    IOSpec,
    ResourceRegistrationStatus,
    register_dataset,
    register_model,
    set_registration_status,
)
from mism_registry.enums import ResourceRegistrationStatus
from mism_registry.operations import set_registration_status


def _approve(registry: InMemoryRegistry, resource):
    """Walk a freshly-registered (DRAFT) resource through the workflow to APPROVED."""
    for target in (
        ResourceRegistrationStatus.ANNOTATING,
        ResourceRegistrationStatus.PENDING_REVIEW,
        ResourceRegistrationStatus.APPROVED,
    ):
        resource = set_registration_status(
            registry, resource_id=resource.id, target=target
        )
    return resource


def _approve(registry: InMemoryRegistry, resource):
    """Walk a freshly registered model through to APPROVED status."""
    for status in (
        ResourceRegistrationStatus.ANNOTATING,
        ResourceRegistrationStatus.PENDING_REVIEW,
        ResourceRegistrationStatus.APPROVED,
    ):
        resource = set_registration_status(registry, resource_id=resource.id, target=status)
    return resource


@pytest.fixture()
def registry() -> InMemoryRegistry:
    """Fresh InMemoryRegistry for each test."""
    return InMemoryRegistry()


@pytest.fixture()
def sample_dataset(registry: InMemoryRegistry):
    """A pre-registered dataset resource."""
    return register_dataset(
        registry,
        name="Test Dataset",
        location_uri="s3://bucket/data.csv",
        format_tags=["csv", "timeseries"],
        owner="test-user",
    )


@pytest.fixture()
def sample_model(registry: InMemoryRegistry):
    """A pre-registered, approved model with IOSpec."""
    model = register_model(
        registry,
        name="Test Model",
        location_uri="docker://registry/model:v1",
        execution_type=ExecutionType.DOCKER,
        version="1.0.0",
        io_spec=IOSpec(
            inputs=(IOSlot(name="input_data", tags=("csv",)),),
            outputs=(IOSlot(name="predictions", tags=("json",)),),
        ),
    )
    return _approve(registry, model)


@pytest.fixture()
def sample_model_no_iospec(registry: InMemoryRegistry):
    """A pre-registered, approved model without IOSpec."""
    model = register_model(
        registry,
        name="Simple Model",
        location_uri="git+https://github.com/org/model@v1",
        execution_type=ExecutionType.PYTHON,
    )
    return _approve(registry, model)
