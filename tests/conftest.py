"""Shared test fixtures."""

import pytest

from mism_registry import (
    ExecutionType,
    InMemoryRegistry,
    IOSlot,
    IOSpec,
    register_dataset,
    register_model,
)


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
    """A pre-registered model with IOSpec."""
    return register_model(
        registry,
        name="Test Model",
        location_uri="docker://registry/model:v1",
        execution_type=ExecutionType.DOCKER_IMAGE,
        version="1.0.0",
        io_spec=IOSpec(
            inputs=(IOSlot(name="input_data", tags=("csv",)),),
            outputs=(IOSlot(name="predictions", tags=("json",)),),
        ),
    )


@pytest.fixture()
def sample_model_no_iospec(registry: InMemoryRegistry):
    """A pre-registered model without IOSpec."""
    return register_model(
        registry,
        name="Simple Model",
        location_uri="git+https://github.com/org/model@v1",
        execution_type=ExecutionType.PYTHON_PACKAGE,
    )
