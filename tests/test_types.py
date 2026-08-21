"""Tests for Author, Publication, IOSlot, IOSpec, RunEnvironment."""

import dataclasses

import pytest

from mism_registry import IOSlot, IOSpec, RunEnvironment
from mism_registry.types import Author, Container, Publication


class TestAuthor:
    def test_creation(self):
        a = Author(name="Alice Smith", orcid="0000-0002-1234-5678", affiliation="NIAID")
        assert a.name == "Alice Smith"
        assert a.orcid == "0000-0002-1234-5678"
        assert a.affiliation == "NIAID"
        assert a.role == ""

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            Author(name="")

    def test_whitespace_name_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            Author(name="   ")

    def test_frozen(self):
        a = Author(name="Bob")
        with pytest.raises(dataclasses.FrozenInstanceError):
            a.name = "Other"  # type: ignore[misc]

    def test_defaults(self):
        a = Author(name="Charlie")
        assert a.orcid == ""
        assert a.affiliation == ""
        assert a.role == ""

    def test_with_role(self):
        a = Author(name="Dev", role="developer")
        assert a.role == "developer"


class TestPublication:
    def test_creation(self):
        p = Publication(title="My Paper", doi="10.1234/test")
        assert p.title == "My Paper"
        assert p.doi == "10.1234/test"
        assert p.url == ""
        assert p.citation == ""

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            Publication(title="")

    def test_whitespace_title_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            Publication(title="   ")

    def test_frozen(self):
        p = Publication(title="Paper")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.title = "Other"  # type: ignore[misc]

    def test_with_url(self):
        p = Publication(title="Preprint", url="https://arxiv.org/abs/1234")
        assert p.url == "https://arxiv.org/abs/1234"


class TestIOSlot:
    def test_creation(self):
        slot = IOSlot(name="sequences", tags=("fasta", "viral"))
        assert slot.name == "sequences"
        assert slot.tags == ("fasta", "viral")
        assert slot.required is True
        assert slot.description == ""

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            IOSlot(name="")

    def test_whitespace_name_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            IOSlot(name="   ")

    def test_tags_normalized_lowercase(self):
        slot = IOSlot(name="data", tags=("FASTA", "Viral"))
        assert slot.tags == ("fasta", "viral")

    def test_tags_deduplicated(self):
        slot = IOSlot(name="data", tags=("csv", "csv", "CSV"))
        assert slot.tags == ("csv",)

    def test_tags_sorted(self):
        slot = IOSlot(name="data", tags=("zebra", "alpha", "mango"))
        assert slot.tags == ("alpha", "mango", "zebra")

    def test_tags_strip_whitespace(self):
        slot = IOSlot(name="data", tags=(" csv ", "json "))
        assert slot.tags == ("csv", "json")

    def test_empty_tags_filtered(self):
        slot = IOSlot(name="data", tags=("csv", "", "  "))
        assert slot.tags == ("csv",)

    def test_frozen(self):
        slot = IOSlot(name="data")
        with pytest.raises(dataclasses.FrozenInstanceError):
            slot.name = "other"  # type: ignore[misc]

    def test_optional_not_required(self):
        slot = IOSlot(name="data", required=False)
        assert slot.required is False


class TestIOSpec:
    def test_creation(self):
        spec = IOSpec(
            inputs=(IOSlot(name="in1"),),
            outputs=(IOSlot(name="out1"),),
        )
        assert len(spec.inputs) == 1
        assert len(spec.outputs) == 1
        assert spec.parameters_schema is None

    def test_empty_is_valid(self):
        spec = IOSpec()
        assert spec.inputs == ()
        assert spec.outputs == ()

    def test_duplicate_input_names_raises(self):
        with pytest.raises(ValueError, match="Duplicate input"):
            IOSpec(
                inputs=(IOSlot(name="data"), IOSlot(name="data")),
            )

    def test_duplicate_output_names_raises(self):
        with pytest.raises(ValueError, match="Duplicate output"):
            IOSpec(
                outputs=(IOSlot(name="result"), IOSlot(name="result")),
            )

    def test_parameters_schema(self):
        schema = {"type": "object", "properties": {"threshold": {"type": "number"}}}
        spec = IOSpec(parameters_schema=schema)
        assert spec.parameters_schema == schema

    def test_frozen(self):
        spec = IOSpec()
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.inputs = ()  # type: ignore[misc]


class TestContainer:
    def test_creation(self):
        c = Container(kind="docker", file="Dockerfile", image_name="mism/model:1.0")
        assert c.kind == "docker"
        assert c.file == "Dockerfile"
        assert c.image_name == "mism/model:1.0"
        assert c.registry == ""

    def test_registry_field(self):
        c = Container(
            kind="docker",
            file="Dockerfile",
            image_name="model:1.0",
            registry="ghcr.io/mism-center",
        )
        assert c.registry == "ghcr.io/mism-center"

    def test_frozen(self):
        c = Container(kind="docker")
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.image_name = "other"  # type: ignore[misc]


class TestRunEnvironment:
    def test_defaults(self):
        env = RunEnvironment()
        assert env.platform == ""
        assert env.container_uri == ""
        assert env.container_digest == ""
        assert env.conda_env == ""
        assert env.hardware_description == ""
        assert env.extra == {}

    def test_with_values(self):
        env = RunEnvironment(
            platform="helx",
            container_uri="docker://img:latest",
            hardware_description="4xA100",
            extra={"nodes": 2},
        )
        assert env.platform == "helx"
        assert env.extra["nodes"] == 2

    def test_extra_independent_per_instance(self):
        env1 = RunEnvironment()
        env2 = RunEnvironment()
        assert env1.extra is not env2.extra
