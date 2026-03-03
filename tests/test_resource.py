"""Tests for the Resource dataclass."""

import uuid
from datetime import timezone

from mism_registry import ExecutionType, IOSpec, Resource, ResourceType


class TestResource:
    def test_auto_uuid(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://bucket/file",
        )
        uuid.UUID(r.id)  # validates it's a proper UUID

    def test_required_fields(self):
        r = Resource(
            name="My Dataset",
            resource_type=ResourceType.DATASET,
            location_uri="s3://bucket/data.csv",
        )
        assert r.name == "My Dataset"
        assert r.resource_type == ResourceType.DATASET
        assert r.location_uri == "s3://bucket/data.csv"

    def test_optional_fields_default(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
        )
        assert r.description == ""
        assert r.version == ""
        assert r.format_tags == []
        assert r.digest_sha256 == ""
        assert r.size_bytes is None
        assert r.execution_type is None
        assert r.execution_ref == ""
        assert r.io_spec is None
        assert r.external_ids == {}
        assert r.license == ""
        assert r.owner == ""
        assert r.metadata == {}

    def test_format_tags_normalized(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            format_tags=["FASTA", "Viral", "fasta"],
        )
        assert r.format_tags == ["fasta", "viral"]

    def test_format_tags_sorted(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            format_tags=["zebra", "alpha"],
        )
        assert r.format_tags == ["alpha", "zebra"]

    def test_timestamps_utc(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
        )
        assert r.created_at.tzinfo == timezone.utc
        assert r.updated_at.tzinfo == timezone.utc

    def test_mutable(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
        )
        r.description = "updated"
        assert r.description == "updated"

    def test_model_with_execution(self):
        r = Resource(
            name="model",
            resource_type=ResourceType.MODEL,
            location_uri="docker://img",
            execution_type=ExecutionType.DOCKER_IMAGE,
            io_spec=IOSpec(),
        )
        assert r.execution_type == ExecutionType.DOCKER_IMAGE
        assert r.io_spec is not None

    def test_external_ids(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            external_ids={"genbank": "MN908947", "doi": "10.1234/test"},
        )
        assert r.external_ids["genbank"] == "MN908947"

    def test_metadata_dict(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            metadata={"resolution_angstroms": 2.5, "organism": "SARS-CoV-2"},
        )
        assert r.metadata["resolution_angstroms"] == 2.5
