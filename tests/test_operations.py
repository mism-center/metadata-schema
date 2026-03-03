"""Tests for high-level operations (public API)."""

import pytest

from mism_registry import (
    ExecutionType,
    InMemoryRegistry,
    IOSlot,
    IOSpec,
    Resource,
    ResourceType,
    RunEnvironment,
    RunStatus,
    cancel_run,
    complete_run,
    fail_run,
    find_resources,
    find_runs,
    get_dependents,
    get_lineage,
    prepare_run,
    register_dataset,
    register_model,
    start_run,
)
from mism_registry.errors import (
    InvalidStateTransitionError,
    IOSpecMismatchError,
    ResourceNotFoundError,
    ValidationError,
)


class TestRegisterDataset:
    def test_happy_path(self, registry: InMemoryRegistry):
        r = register_dataset(
            registry,
            name="My Data",
            location_uri="s3://bucket/data.csv",
            format_tags=["csv", "timeseries"],
            owner="alice",
        )
        assert r.name == "My Data"
        assert r.resource_type == ResourceType.DATASET
        assert r.format_tags == ["csv", "timeseries"]

    def test_empty_name_raises(self, registry: InMemoryRegistry):
        with pytest.raises(ValidationError, match="name"):
            register_dataset(registry, name="", location_uri="s3://x")

    def test_empty_location_raises(self, registry: InMemoryRegistry):
        with pytest.raises(ValidationError, match="location_uri"):
            register_dataset(registry, name="test", location_uri="")

    def test_minimal_registration(self, registry: InMemoryRegistry):
        r = register_dataset(registry, name="test", location_uri="s3://x")
        assert r.resource_type == ResourceType.DATASET
        assert r.format_tags == []

    def test_with_all_optional_fields(self, registry: InMemoryRegistry):
        r = register_dataset(
            registry,
            name="Full Dataset",
            location_uri="s3://bucket/full.csv",
            description="A complete dataset",
            version="1.0.0",
            format_tags=["csv"],
            digest_sha256="abc123",
            size_bytes=1024,
            external_ids={"doi": "10.1234/test"},
            license="CC-BY-4.0",
            owner="alice",
            metadata={"source": "lab"},
        )
        assert r.description == "A complete dataset"
        assert r.version == "1.0.0"
        assert r.digest_sha256 == "abc123"
        assert r.size_bytes == 1024
        assert r.external_ids["doi"] == "10.1234/test"
        assert r.license == "CC-BY-4.0"
        assert r.metadata["source"] == "lab"


class TestRegisterModel:
    def test_happy_path(self, registry: InMemoryRegistry):
        r = register_model(
            registry,
            name="My Model",
            location_uri="docker://img:v1",
            execution_type=ExecutionType.DOCKER_IMAGE,
            io_spec=IOSpec(
                inputs=(IOSlot(name="data", tags=("csv",)),),
            ),
        )
        assert r.resource_type == ResourceType.MODEL
        assert r.execution_type == ExecutionType.DOCKER_IMAGE
        assert r.io_spec is not None

    def test_warns_without_iospec(self, registry: InMemoryRegistry):
        with pytest.warns(UserWarning, match="no io_spec"):
            register_model(
                registry,
                name="Model",
                location_uri="docker://img",
                execution_type=ExecutionType.DOCKER_IMAGE,
            )

    def test_register_tool(self, registry: InMemoryRegistry):
        r = register_model(
            registry,
            name="My Tool",
            location_uri="docker://tool:v1",
            execution_type=ExecutionType.SHELL_COMMAND,
            resource_type=ResourceType.TOOL,
            io_spec=IOSpec(),
        )
        assert r.resource_type == ResourceType.TOOL

    def test_dataset_type_rejected(self, registry: InMemoryRegistry):
        with pytest.raises(ValidationError, match="MODEL or TOOL"):
            register_model(
                registry,
                name="Bad",
                location_uri="s3://x",
                execution_type=ExecutionType.OTHER,
                resource_type=ResourceType.DATASET,
            )


class TestPrepareRun:
    def test_happy_path(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
            parameters={"threshold": 0.5},
            environment=RunEnvironment(platform="helx"),
            triggered_by="alice",
        )
        assert run.status == RunStatus.REGISTERED
        assert run.model_id == sample_model.id
        assert run.model_version == "1.0.0"
        assert run.input_resource_ids == [sample_dataset.id]
        assert run.parameters["threshold"] == 0.5

    def test_model_not_found(self, registry: InMemoryRegistry, sample_dataset):
        with pytest.raises(ResourceNotFoundError):
            prepare_run(
                registry,
                model_id="nonexistent",
                input_resource_ids=[sample_dataset.id],
            )

    def test_input_not_found(self, registry: InMemoryRegistry, sample_model):
        with pytest.raises(ResourceNotFoundError):
            prepare_run(
                registry,
                model_id=sample_model.id,
                input_resource_ids=["nonexistent"],
            )

    def test_dataset_as_model_rejected(
        self, registry: InMemoryRegistry, sample_dataset
    ):
        with pytest.raises(ValidationError, match="not a model"):
            prepare_run(
                registry,
                model_id=sample_dataset.id,
                input_resource_ids=[],
            )

    def test_iospec_mismatch(self, registry: InMemoryRegistry, sample_model):
        bad_input = register_dataset(
            registry,
            name="Wrong Format",
            location_uri="s3://x",
            format_tags=["fasta"],
        )
        with pytest.raises(IOSpecMismatchError):
            prepare_run(
                registry,
                model_id=sample_model.id,
                input_resource_ids=[bad_input.id],
            )

    def test_no_iospec_warns(
        self, registry: InMemoryRegistry, sample_model_no_iospec, sample_dataset
    ):
        with pytest.warns(UserWarning, match="no io_spec"):
            prepare_run(
                registry,
                model_id=sample_model_no_iospec.id,
                input_resource_ids=[sample_dataset.id],
            )

    def test_no_iospec_no_inputs_no_warning(
        self, registry: InMemoryRegistry, sample_model_no_iospec
    ):
        # No inputs means no warning needed
        run = prepare_run(
            registry,
            model_id=sample_model_no_iospec.id,
            input_resource_ids=[],
        )
        assert run.status == RunStatus.REGISTERED


class TestStartRun:
    def test_happy_path(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        started = start_run(registry, run_id=run.id)
        assert started.status == RunStatus.RUNNING
        assert started.started_at is not None


class TestCompleteRun:
    def test_happy_path(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        run = start_run(registry, run_id=run.id)
        output = Resource(
            name="Output",
            resource_type=ResourceType.DATASET,
            location_uri="s3://results/output.json",
            format_tags=["json"],
        )
        completed = complete_run(
            registry, run_id=run.id, output_resources=[output]
        )
        assert completed.status == RunStatus.COMPLETED
        assert len(completed.output_resource_ids) == 1
        assert completed.completed_at is not None

    def test_from_registered_raises(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        with pytest.raises(InvalidStateTransitionError):
            complete_run(registry, run_id=run.id, output_resources=[])


class TestFailRun:
    def test_happy_path(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        run = start_run(registry, run_id=run.id)
        failed = fail_run(
            registry,
            run_id=run.id,
            error_message="OOM",
            log_uri="s3://logs/run.log",
        )
        assert failed.status == RunStatus.FAILED
        assert failed.error_message == "OOM"
        assert failed.log_uri == "s3://logs/run.log"
        assert failed.completed_at is not None


class TestCancelRun:
    def test_from_registered(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        cancelled = cancel_run(registry, run_id=run.id)
        assert cancelled.status == RunStatus.CANCELLED

    def test_from_running(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        run = start_run(registry, run_id=run.id)
        cancelled = cancel_run(registry, run_id=run.id)
        assert cancelled.status == RunStatus.CANCELLED

    def test_from_completed_raises(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        run = start_run(registry, run_id=run.id)
        complete_run(registry, run_id=run.id, output_resources=[])
        with pytest.raises(InvalidStateTransitionError):
            cancel_run(registry, run_id=run.id)


class TestDiscovery:
    def test_find_resources_delegates(self, registry: InMemoryRegistry):
        register_dataset(registry, name="d1", location_uri="s3://a")
        register_dataset(
            registry, name="d2", location_uri="s3://b", format_tags=["csv"]
        )
        results = find_resources(registry, tags=["csv"])
        assert len(results) == 1

    def test_find_runs_delegates(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        results = find_runs(registry, model_id=sample_model.id)
        assert len(results) == 1

    def test_get_lineage_delegates(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        run = start_run(registry, run_id=run.id)
        output = Resource(
            name="out",
            resource_type=ResourceType.DATASET,
            location_uri="s3://out",
        )
        completed = complete_run(
            registry, run_id=run.id, output_resources=[output]
        )
        lineage = get_lineage(registry, completed.output_resource_ids[0])
        assert len(lineage) == 1

    def test_get_dependents_delegates(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        deps = get_dependents(registry, sample_dataset.id)
        assert len(deps) == 1
