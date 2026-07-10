"""Tests for high-level operations (public API)."""

import pytest

from mism_registry import (
    ExecutionType,
    InMemoryRegistry,
    IOSlot,
    IOSpec,
    ModelRunSummary,
    Resource,
    ResourceRegistrationStatus,
    ResourceType,
    ResourceVersionStatus,
    RunEnvironment,
    RunStatus,
    cancel_run,
    complete_run,
    create_new_version,
    fail_run,
    find_resources,
    find_runs,
    get_dependents,
    get_latest_version,
    get_lineage,
    get_model_run_details,
    get_version_history,
    prepare_run,
    register_dataset,
    register_model,
    set_registration_status,
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
            execution_type=ExecutionType.DOCKER,
            io_spec=IOSpec(
                inputs=(IOSlot(name="data", tags=("csv",)),),
            ),
        )
        assert r.resource_type == ResourceType.MODEL
        assert r.execution_type == ExecutionType.DOCKER
        assert r.io_spec is not None

    def test_warns_without_iospec(self, registry: InMemoryRegistry):
        with pytest.warns(UserWarning, match="no io_spec"):
            register_model(
                registry,
                name="Model",
                location_uri="docker://img",
                execution_type=ExecutionType.DOCKER,
            )

    def test_register_tool(self, registry: InMemoryRegistry):
        r = register_model(
            registry,
            name="My Tool",
            location_uri="docker://tool:v1",
            execution_type=ExecutionType.BINARY,
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


class TestCreateNewVersion:
    def test_happy_path(self, registry: InMemoryRegistry):
        original = register_dataset(
            registry,
            name="Dataset",
            location_uri="s3://v1",
            version="1.0",
            owner="alice",
            organisms=["SARS-CoV-2"],
        )
        new = create_new_version(
            registry,
            original_id=original.id,
            location_uri="s3://v2",
            version="2.0",
        )
        assert new.name == "Dataset"
        assert new.location_uri == "s3://v2"
        assert new.version == "2.0"
        assert new.new_version_of == original.id
        assert new.version_status == ResourceVersionStatus.ACTIVE
        # Carries forward inherited fields
        assert new.owner == "alice"
        assert new.organisms == ["SARS-CoV-2"]

        # Original is now superseded
        updated_original = registry.get_resource(original.id)
        assert updated_original.version_status == ResourceVersionStatus.SUPERSEDED
        assert updated_original.superseded_by == new.id

    def test_inherits_metadata(self, registry: InMemoryRegistry):
        original = register_dataset(
            registry,
            name="D",
            location_uri="s3://v1",
            description="Original desc",
            metadata={"key": "value"},
        )
        new = create_new_version(registry, original_id=original.id, location_uri="s3://v2")
        assert new.description == "Original desc"
        assert new.metadata["key"] == "value"

    def test_override_description(self, registry: InMemoryRegistry):
        original = register_dataset(
            registry,
            name="D",
            location_uri="s3://v1",
            description="Old desc",
        )
        new = create_new_version(
            registry,
            original_id=original.id,
            location_uri="s3://v2",
            description="New desc",
        )
        assert new.description == "New desc"

    def test_superseded_resource_rejects_version(self, registry: InMemoryRegistry):
        v1 = register_dataset(registry, name="D", location_uri="s3://v1")
        create_new_version(registry, original_id=v1.id, location_uri="s3://v2")
        # v1 is now superseded, so creating another version from it should fail
        with pytest.raises(ValidationError, match="active"):
            create_new_version(registry, original_id=v1.id, location_uri="s3://v3")

    def test_nonexistent_original_raises(self, registry: InMemoryRegistry):
        with pytest.raises(ResourceNotFoundError):
            create_new_version(registry, original_id="nonexistent", location_uri="s3://v2")


class TestGetLatestVersion:
    def test_single_version(self, registry: InMemoryRegistry):
        r = register_dataset(registry, name="D", location_uri="s3://v1")
        latest = get_latest_version(registry, r.id)
        assert latest is not None
        assert latest.id == r.id

    def test_version_chain(self, registry: InMemoryRegistry):
        v1 = register_dataset(registry, name="D", location_uri="s3://v1")
        v2 = create_new_version(registry, original_id=v1.id, location_uri="s3://v2")
        latest = get_latest_version(registry, v1.id)
        assert latest is not None
        assert latest.id == v2.id

    def test_nonexistent(self, registry: InMemoryRegistry):
        assert get_latest_version(registry, "nonexistent") is None


class TestGetVersionHistory:
    def test_single_version(self, registry: InMemoryRegistry):
        r = register_dataset(registry, name="D", location_uri="s3://v1")
        history = get_version_history(registry, r.id)
        assert len(history) == 1
        assert history[0].id == r.id

    def test_version_chain(self, registry: InMemoryRegistry):
        v1 = register_dataset(registry, name="D", location_uri="s3://v1")
        v2 = create_new_version(registry, original_id=v1.id, location_uri="s3://v2")
        v3 = create_new_version(registry, original_id=v2.id, location_uri="s3://v3")
        # Query from any point in the chain
        for rid in [v1.id, v2.id, v3.id]:
            history = get_version_history(registry, rid)
            assert len(history) == 3
            assert history[0].id == v1.id
            assert history[1].id == v2.id
            assert history[2].id == v3.id

    def test_nonexistent(self, registry: InMemoryRegistry):
        assert get_version_history(registry, "nonexistent") == []


class TestPrepareRun:
    def test_happy_path(self, registry: InMemoryRegistry, sample_dataset, sample_model):
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

    def test_dataset_as_model_rejected(self, registry: InMemoryRegistry, sample_dataset):
        with pytest.raises(ValidationError, match="not a model"):
            prepare_run(
                registry,
                model_id=sample_dataset.id,
                input_resource_ids=[],
            )

    def test_unapproved_model_rejected(self, registry: InMemoryRegistry, sample_model):
        # Model still mid-registration (agent building metadata-package) — not runnable.
        sample_model.registration_status = ResourceRegistrationStatus.PENDING_REVIEW
        registry.update_resource(sample_model)
        with pytest.raises(ValidationError, match="approved"):
            prepare_run(
                registry,
                model_id=sample_model.id,
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

    def test_superseded_model_rejected(self, registry: InMemoryRegistry):
        model = register_model(
            registry,
            name="Model",
            location_uri="docker://img:v1",
            execution_type=ExecutionType.DOCKER,
            io_spec=IOSpec(),
        )
        # Create a new version to supersede the original
        create_new_version(registry, original_id=model.id, location_uri="docker://img:v2")
        dataset = register_dataset(registry, name="Data", location_uri="s3://d")
        with pytest.raises(ValidationError, match="active"):
            prepare_run(
                registry,
                model_id=model.id,
                input_resource_ids=[dataset.id],
            )

    def test_superseded_input_rejected(self, registry: InMemoryRegistry):
        dataset = register_dataset(registry, name="Data", location_uri="s3://v1")
        create_new_version(registry, original_id=dataset.id, location_uri="s3://v2")
        model = register_model(
            registry,
            name="Model",
            location_uri="docker://img",
            execution_type=ExecutionType.DOCKER,
            io_spec=IOSpec(),
        )
        for status in (
            ResourceRegistrationStatus.ANNOTATING,
            ResourceRegistrationStatus.PENDING_REVIEW,
            ResourceRegistrationStatus.APPROVED,
        ):
            model = set_registration_status(registry, resource_id=model.id, target=status)
        with pytest.raises(ValidationError, match="active"):
            prepare_run(
                registry,
                model_id=model.id,
                input_resource_ids=[dataset.id],
            )


class TestStartRun:
    def test_happy_path(self, registry: InMemoryRegistry, sample_dataset, sample_model):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        started = start_run(registry, run_id=run.id)
        assert started.status == RunStatus.RUNNING
        assert started.started_at is not None


class TestCompleteRun:
    def test_happy_path(self, registry: InMemoryRegistry, sample_dataset, sample_model):
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
        completed = complete_run(registry, run_id=run.id, output_resources=[output])
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
    def test_happy_path(self, registry: InMemoryRegistry, sample_dataset, sample_model):
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
    def test_from_registered(self, registry: InMemoryRegistry, sample_dataset, sample_model):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        cancelled = cancel_run(registry, run_id=run.id)
        assert cancelled.status == RunStatus.CANCELLED

    def test_from_running(self, registry: InMemoryRegistry, sample_dataset, sample_model):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        run = start_run(registry, run_id=run.id)
        cancelled = cancel_run(registry, run_id=run.id)
        assert cancelled.status == RunStatus.CANCELLED

    def test_from_completed_raises(self, registry: InMemoryRegistry, sample_dataset, sample_model):
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
        register_dataset(registry, name="d2", location_uri="s3://b", format_tags=["csv"])
        results = find_resources(registry, tags=["csv"])
        assert len(results) == 1

    def test_find_runs_delegates(self, registry: InMemoryRegistry, sample_dataset, sample_model):
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        results = find_runs(registry, model_id=sample_model.id)
        assert len(results) == 1

    def test_get_lineage_delegates(self, registry: InMemoryRegistry, sample_dataset, sample_model):
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
        completed = complete_run(registry, run_id=run.id, output_resources=[output])
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


class TestGetModelRunDetails:
    def test_completed_run_with_outputs(
        self, registry: InMemoryRegistry, sample_dataset, sample_model
    ):
        run = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        run = start_run(registry, run_id=run.id)
        output = Resource(
            name="Predictions",
            resource_type=ResourceType.DATASET,
            location_uri="s3://results/predictions.json",
            format_tags=["json"],
        )
        complete_run(registry, run_id=run.id, output_resources=[output])

        summary = get_model_run_details(registry, model_id=sample_model.id)

        assert isinstance(summary, ModelRunSummary)
        assert summary.model.id == sample_model.id
        assert summary.model.name == "Test Model"
        assert len(summary.runs) == 1

        detail = summary.runs[0]
        assert detail.run.model_id == sample_model.id
        assert detail.run.status == RunStatus.COMPLETED
        assert len(detail.input_resources) == 1
        assert detail.input_resources[0].id == sample_dataset.id
        assert detail.input_resources[0].name == "Test Dataset"
        assert len(detail.output_resources) == 1
        assert detail.output_resources[0].name == "Predictions"

    def test_no_runs_returns_empty(self, registry: InMemoryRegistry, sample_model):
        summary = get_model_run_details(registry, model_id=sample_model.id)
        assert summary.model.id == sample_model.id
        assert summary.runs == []

    def test_multiple_runs(self, registry: InMemoryRegistry, sample_dataset, sample_model):
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        summary = get_model_run_details(registry, model_id=sample_model.id)
        assert len(summary.runs) == 2

    def test_filter_by_status(self, registry: InMemoryRegistry, sample_dataset, sample_model):
        run1 = prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        start_run(registry, run_id=run1.id)
        # run2 stays REGISTERED
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )

        summary = get_model_run_details(
            registry, model_id=sample_model.id, status=RunStatus.RUNNING
        )
        assert len(summary.runs) == 1
        assert summary.runs[0].run.status == RunStatus.RUNNING

    def test_nonexistent_model_raises(self, registry: InMemoryRegistry):
        with pytest.raises(ResourceNotFoundError):
            get_model_run_details(registry, model_id="nonexistent")

    def test_dataset_as_model_raises(self, registry: InMemoryRegistry, sample_dataset):
        with pytest.raises(ValidationError, match="not a model"):
            get_model_run_details(registry, model_id=sample_dataset.id)

    def test_superseded_model_allowed(self, registry: InMemoryRegistry):
        model = register_model(
            registry,
            name="Model",
            location_uri="docker://img:v1",
            execution_type=ExecutionType.DOCKER,
            io_spec=IOSpec(),
        )
        create_new_version(registry, original_id=model.id, location_uri="docker://img:v2")
        # model is now SUPERSEDED — should still be queryable
        summary = get_model_run_details(registry, model_id=model.id)
        assert summary.model.version_status == ResourceVersionStatus.SUPERSEDED
        assert summary.runs == []

    def test_shared_input_hydrated(self, registry: InMemoryRegistry, sample_dataset, sample_model):
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        summary = get_model_run_details(registry, model_id=sample_model.id)
        assert len(summary.runs) == 2
        assert summary.runs[0].input_resources[0].id == sample_dataset.id
        assert summary.runs[1].input_resources[0].id == sample_dataset.id

    def test_run_with_no_outputs(self, registry: InMemoryRegistry, sample_dataset, sample_model):
        prepare_run(
            registry,
            model_id=sample_model.id,
            input_resource_ids=[sample_dataset.id],
        )
        summary = get_model_run_details(registry, model_id=sample_model.id)
        assert summary.runs[0].output_resources == []

    def test_tool_accepted(self, registry: InMemoryRegistry):
        tool = register_model(
            registry,
            name="Converter Tool",
            location_uri="docker://tool:v1",
            execution_type=ExecutionType.BINARY,
            resource_type=ResourceType.TOOL,
            io_spec=IOSpec(),
        )
        summary = get_model_run_details(registry, model_id=tool.id)
        assert summary.model.resource_type == ResourceType.TOOL
        assert summary.runs == []


class TestSetRegistrationStatus:
    def _draft_model(self, registry: InMemoryRegistry) -> Resource:
        model = Resource(
            name="draft-model",
            resource_type=ResourceType.MODEL,
            location_uri="s3://uploads/model.zip",
            execution_type=ExecutionType.PYTHON,
            registration_status=ResourceRegistrationStatus.DRAFT,
        )
        return registry.register_resource(model)

    def test_walk_happy_path(self, registry: InMemoryRegistry):
        model = self._draft_model(registry)
        for target in (
            ResourceRegistrationStatus.ANNOTATING,
            ResourceRegistrationStatus.PENDING_REVIEW,
            ResourceRegistrationStatus.APPROVED,
        ):
            updated = set_registration_status(registry, resource_id=model.id, target=target)
            assert updated.registration_status == target

    def test_illegal_transition_raises(self, registry: InMemoryRegistry):
        model = self._draft_model(registry)  # DRAFT
        with pytest.raises(InvalidStateTransitionError):
            set_registration_status(
                registry,
                resource_id=model.id,
                target=ResourceRegistrationStatus.APPROVED,  # can't skip the workflow
            )
