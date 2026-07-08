"""Tests for enumerations."""

from mism_registry import (
    ExecutionType,
    ResourceRegistrationStatus,
    ResourceType,
    ResourceVersionStatus,
    RunStatus,
)


class TestResourceType:
    def test_members(self):
        assert set(ResourceType) == {
            ResourceType.DATASET,
            ResourceType.MODEL,
            ResourceType.TOOL,
        }

    def test_values_are_lowercase(self):
        for member in ResourceType:
            assert member.value == member.value.lower()

    def test_str_serialization(self):
        assert ResourceType.DATASET.value == "dataset"
        assert ResourceType.MODEL.value == "model"
        assert ResourceType.TOOL.value == "tool"


class TestExecutionType:
    def test_members(self):
        expected = {
            "docker",
            "conda",
            "pip",
            "python",
            "r",
            "binary",
            "huggingface",
            "notebook",
            "singularity",
            "nextflow",
            "snakemake",
            "jupyter",
            "native",
            "other",
        }
        assert {e.value for e in ExecutionType} == expected

    def test_values_are_lowercase(self):
        for member in ExecutionType:
            assert member.value == member.value.lower()


class TestResourceVersionStatus:
    def test_members(self):
        expected = {"active", "superseded", "archived"}
        assert {s.value for s in ResourceVersionStatus} == expected

    def test_values_are_lowercase(self):
        for member in ResourceVersionStatus:
            assert member.value == member.value.lower()

    def test_is_str_subclass(self):
        assert isinstance(ResourceVersionStatus.ACTIVE, str)


class TestResourceRegistrationStatus:
    def test_members(self):
        expected = {
            "draft",
            "annotating",
            "annotation_failed",
            "pending_review",
            "rejected",
            "approved",
        }
        assert {s.value for s in ResourceRegistrationStatus} == expected

    def test_values_are_lowercase(self):
        for member in ResourceRegistrationStatus:
            assert member.value == member.value.lower()


class TestRunStatus:
    def test_members(self):
        expected = {"registered", "running", "completed", "failed", "cancelled"}
        assert {s.value for s in RunStatus} == expected

    def test_values_are_lowercase(self):
        for member in RunStatus:
            assert member.value == member.value.lower()

    def test_is_str_subclass(self):
        assert isinstance(RunStatus.COMPLETED, str)
