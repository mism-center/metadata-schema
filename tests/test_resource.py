"""Tests for the Resource dataclass."""

import uuid
from datetime import date, timezone

from mism_registry import (
    ExecutionType,
    ImageReviewStatus,
    IOSpec,
    Resource,
    ResourceRegistrationStatus,
    ResourceType,
    ResourceVersionStatus,
)
from mism_registry.types import Author, Publication


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
        assert r.version_status == ResourceVersionStatus.ACTIVE
        # Programmatic construction defaults to DRAFT (workflow promotes it).
        assert r.registration_status == ResourceRegistrationStatus.DRAFT
        assert r.metadata_reviewed_by == ""
        assert r.metadata_reviewed_at is None
        assert r.metadata_rejection_reason == ""
        assert r.new_version_of == ""
        assert r.superseded_by == ""
        # Image review workflow (MISM-291) — inert until a Container is shipped.
        assert r.image_review_status == ImageReviewStatus.NOT_APPLICABLE
        assert r.image_reviewed_by == ""
        assert r.image_reviewed_at is None
        assert r.image_rejection_reason == ""
        assert r.format_tags == []
        assert r.digest_sha256 == ""
        assert r.size_bytes is None
        assert r.execution_type is None
        assert r.execution_ref == ""
        assert r.io_spec is None
        assert r.external_ids == {}
        assert r.license == ""
        # Source provenance — empty unless the resource was imported upstream.
        assert r.source_repository == ""
        assert r.source_identifier == ""
        assert r.source_url == ""
        assert r.source_revision == ""
        assert r.owner == ""
        assert r.metadata == {}
        # Authorship
        assert r.authors == []
        assert r.organization == ""
        assert r.contact_email == ""
        assert r.publications == []
        assert r.funding == []
        # Scientific context
        assert r.model_scales == []
        assert r.organisms == []
        assert r.domains == []
        assert r.date_published is None

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
            execution_type=ExecutionType.DOCKER,
            io_spec=IOSpec(),
        )
        assert r.execution_type == ExecutionType.DOCKER
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

    def test_authorship_fields(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            authors=[Author(name="Alice", orcid="0000-0001-2345-6789")],
            organization="NIAID VRC",
            contact_email="alice@niaid.nih.gov",
            publications=[Publication(title="My Paper", doi="10.1234/test")],
            funding=["NIAID U19 AI123456"],
        )
        assert len(r.authors) == 1
        assert r.authors[0].name == "Alice"
        assert r.organization == "NIAID VRC"
        assert r.contact_email == "alice@niaid.nih.gov"
        assert len(r.publications) == 1
        assert r.funding == ["NIAID U19 AI123456"]

    def test_scientific_context_fields(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            model_scales=["molecular", "cellular"],
            organisms=["SARS-CoV-2", "Homo sapiens"],
            domains=["structural-biology", "immunology"],
            date_published=date(2026, 1, 15),
        )
        assert r.model_scales == ["molecular", "cellular"]
        assert r.organisms == ["SARS-CoV-2", "Homo sapiens"]
        assert r.domains == ["structural-biology", "immunology"]
        assert r.date_published == date(2026, 1, 15)

    def test_versioning_fields(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            version_status=ResourceVersionStatus.SUPERSEDED,
            new_version_of="old-uuid",
            superseded_by="new-uuid",
        )
        assert r.version_status == ResourceVersionStatus.SUPERSEDED
        assert r.new_version_of == "old-uuid"
        assert r.superseded_by == "new-uuid"

    def test_metadata_review_fields(self):
        r = Resource(
            name="test",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            registration_status=ResourceRegistrationStatus.REJECTED,
            metadata_reviewed_by="erin",
            metadata_rejection_reason="missing execution.yaml",
        )
        assert r.registration_status == ResourceRegistrationStatus.REJECTED
        assert r.metadata_reviewed_by == "erin"
        assert r.metadata_rejection_reason == "missing execution.yaml"

    def test_image_review_fields(self):
        r = Resource(
            name="model",
            resource_type=ResourceType.MODEL,
            location_uri="docker://img",
            image_review_status=ImageReviewStatus.IMAGE_REJECTED,
            image_reviewed_by="frank",
            image_rejection_reason="base image not pinned",
        )
        assert r.image_review_status == ImageReviewStatus.IMAGE_REJECTED
        assert r.image_reviewed_by == "frank"
        assert r.image_rejection_reason == "base image not pinned"
