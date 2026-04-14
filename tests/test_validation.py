"""Tests for validation helpers."""

import pytest

from mism_registry import (
    ExecutionType,
    IOSlot,
    IOSpec,
    Resource,
    ResourceStatus,
    ResourceType,
    RunStatus,
)
from mism_registry.errors import (
    InvalidStateTransitionError,
    IOSpecMismatchError,
    ValidationError,
)
from mism_registry.validation import (
    check_iospec_handshake,
    normalize_tags,
    validate_execution_fields,
    validate_resource_is_active,
    validate_resource_required_fields,
    validate_run_status_transition,
)


class TestValidateResourceRequiredFields:
    def test_valid_resource(self):
        r = Resource(name="test", resource_type=ResourceType.DATASET, location_uri="s3://x")
        validate_resource_required_fields(r)  # Should not raise

    def test_empty_name_raises(self):
        r = Resource(name="", resource_type=ResourceType.DATASET, location_uri="s3://x")
        with pytest.raises(ValidationError, match="name"):
            validate_resource_required_fields(r)

    def test_whitespace_name_raises(self):
        r = Resource(name="   ", resource_type=ResourceType.DATASET, location_uri="s3://x")
        with pytest.raises(ValidationError, match="name"):
            validate_resource_required_fields(r)

    def test_empty_location_uri_raises(self):
        r = Resource(name="test", resource_type=ResourceType.DATASET, location_uri="")
        with pytest.raises(ValidationError, match="location_uri"):
            validate_resource_required_fields(r)

    def test_whitespace_location_uri_raises(self):
        r = Resource(name="test", resource_type=ResourceType.DATASET, location_uri="   ")
        with pytest.raises(ValidationError, match="location_uri"):
            validate_resource_required_fields(r)


class TestValidateExecutionFields:
    def test_dataset_no_execution_type_ok(self):
        r = Resource(name="test", resource_type=ResourceType.DATASET, location_uri="s3://x")
        validate_execution_fields(r)  # Should not raise

    def test_model_without_execution_type_raises(self):
        r = Resource(name="test", resource_type=ResourceType.MODEL, location_uri="s3://x")
        with pytest.raises(ValidationError, match="execution_type"):
            validate_execution_fields(r)

    def test_tool_without_execution_type_raises(self):
        r = Resource(name="test", resource_type=ResourceType.TOOL, location_uri="s3://x")
        with pytest.raises(ValidationError, match="execution_type"):
            validate_execution_fields(r)

    def test_model_without_iospec_warns(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.MODEL,
            location_uri="s3://x",
            execution_type=ExecutionType.DOCKER,
        )
        with pytest.warns(UserWarning, match="no io_spec"):
            validate_execution_fields(r)

    def test_model_with_iospec_no_warning(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.MODEL,
            location_uri="s3://x",
            execution_type=ExecutionType.DOCKER,
            io_spec=IOSpec(),
        )
        # Should not warn
        validate_execution_fields(r)


class TestValidateResourceIsActive:
    def test_active_resource_passes(self):
        r = Resource(name="test", resource_type=ResourceType.DATASET, location_uri="s3://x")
        validate_resource_is_active(r)  # Should not raise

    def test_superseded_resource_raises(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            status=ResourceStatus.SUPERSEDED,
        )
        with pytest.raises(ValidationError, match="active"):
            validate_resource_is_active(r)

    def test_archived_resource_raises(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            status=ResourceStatus.ARCHIVED,
        )
        with pytest.raises(ValidationError, match="active"):
            validate_resource_is_active(r)


class TestNormalizeTags:
    def test_lowercase(self):
        assert normalize_tags(["FASTA", "CSV"]) == ["csv", "fasta"]

    def test_deduplicate(self):
        assert normalize_tags(["csv", "csv", "CSV"]) == ["csv"]

    def test_sort(self):
        assert normalize_tags(["zebra", "alpha"]) == ["alpha", "zebra"]

    def test_strip_whitespace(self):
        assert normalize_tags([" csv ", " json "]) == ["csv", "json"]

    def test_empty_input(self):
        assert normalize_tags([]) == []

    def test_filter_empty_strings(self):
        assert normalize_tags(["csv", "", "  "]) == ["csv"]


class TestCheckIOSpecHandshake:
    def _make_resource(self, tags: list[str]) -> Resource:
        return Resource(
            name="data",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            format_tags=tags,
        )

    def test_matching_tags(self):
        spec = IOSpec(inputs=(IOSlot(name="in", tags=("csv", "timeseries")),))
        resources = [self._make_resource(["csv", "timeseries", "extra"])]
        check_iospec_handshake(spec, resources)  # Should not raise

    def test_exact_match(self):
        spec = IOSpec(inputs=(IOSlot(name="in", tags=("csv",)),))
        resources = [self._make_resource(["csv"])]
        check_iospec_handshake(spec, resources)

    def test_missing_tag_raises(self):
        spec = IOSpec(inputs=(IOSlot(name="in", tags=("csv", "timeseries")),))
        resources = [self._make_resource(["csv"])]
        with pytest.raises(IOSpecMismatchError, match="in"):
            check_iospec_handshake(spec, resources)

    def test_no_matching_resource_raises(self):
        spec = IOSpec(inputs=(IOSlot(name="in", tags=("fasta",)),))
        resources = [self._make_resource(["csv"])]
        with pytest.raises(IOSpecMismatchError):
            check_iospec_handshake(spec, resources)

    def test_optional_slot_skipped(self):
        spec = IOSpec(inputs=(IOSlot(name="optional_in", tags=("fasta",), required=False),))
        resources = [self._make_resource(["csv"])]
        check_iospec_handshake(spec, resources)  # Should not raise

    def test_slot_with_no_tags_skipped(self):
        spec = IOSpec(inputs=(IOSlot(name="any_data"),))
        resources = [self._make_resource(["csv"])]
        check_iospec_handshake(spec, resources)  # Should not raise

    def test_multiple_resources_one_matches(self):
        spec = IOSpec(inputs=(IOSlot(name="in", tags=("fasta", "viral")),))
        resources = [
            self._make_resource(["csv"]),
            self._make_resource(["fasta", "viral", "spike"]),
        ]
        check_iospec_handshake(spec, resources)

    def test_multiple_slots_all_satisfied(self):
        spec = IOSpec(
            inputs=(
                IOSlot(name="sequences", tags=("fasta",)),
                IOSlot(name="structure", tags=("pdb",)),
            )
        )
        resources = [
            self._make_resource(["fasta", "viral"]),
            self._make_resource(["pdb", "protein"]),
        ]
        check_iospec_handshake(spec, resources)

    def test_multiple_slots_one_unsatisfied(self):
        spec = IOSpec(
            inputs=(
                IOSlot(name="sequences", tags=("fasta",)),
                IOSlot(name="structure", tags=("pdb",)),
            )
        )
        resources = [self._make_resource(["fasta", "viral"])]
        with pytest.raises(IOSpecMismatchError, match="structure"):
            check_iospec_handshake(spec, resources)


class TestValidateRunStatusTransition:
    def test_registered_to_running(self):
        validate_run_status_transition(RunStatus.REGISTERED, RunStatus.RUNNING)

    def test_registered_to_cancelled(self):
        validate_run_status_transition(RunStatus.REGISTERED, RunStatus.CANCELLED)

    def test_running_to_completed(self):
        validate_run_status_transition(RunStatus.RUNNING, RunStatus.COMPLETED)

    def test_running_to_failed(self):
        validate_run_status_transition(RunStatus.RUNNING, RunStatus.FAILED)

    def test_running_to_cancelled(self):
        validate_run_status_transition(RunStatus.RUNNING, RunStatus.CANCELLED)

    def test_completed_to_running_raises(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_run_status_transition(RunStatus.COMPLETED, RunStatus.RUNNING)

    def test_failed_to_running_raises(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_run_status_transition(RunStatus.FAILED, RunStatus.RUNNING)

    def test_cancelled_to_running_raises(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_run_status_transition(RunStatus.CANCELLED, RunStatus.RUNNING)

    def test_registered_to_completed_raises(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_run_status_transition(RunStatus.REGISTERED, RunStatus.COMPLETED)

    def test_all_terminal_states_reject_transitions(self):
        terminal = [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]
        for current in terminal:
            for target in RunStatus:
                if target != current:
                    with pytest.raises(InvalidStateTransitionError):
                        validate_run_status_transition(current, target)
