"""Tests for PostgresRegistry backend.

Requires a running Postgres instance. Set MISM_TEST_DATABASE_URL to enable:

    export MISM_TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/mism_test
    uv run pytest tests/test_postgres_backend.py -v
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mism_registry import (
    Author,
    ExecutionType,
    IOSlot,
    IOSpec,
    Publication,
    Resource,
    ResourceStatus,
    ResourceType,
    Run,
    RunEnvironment,
    RunStatus,
)
from mism_registry.backends.postgres import Base, PostgresRegistry
from mism_registry.errors import (
    DuplicateResourceError,
    ResourceNotFoundError,
    RunNotFoundError,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def pg_engine():
    url = os.environ.get("MISM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("MISM_TEST_DATABASE_URL not set")
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def pg_session(pg_engine):
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def pg_registry(pg_session):
    return PostgresRegistry(pg_session)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_dataset(
    name: str = "Test Dataset",
    location_uri: str = "s3://bucket/data.csv",
    **kwargs,
) -> Resource:
    return Resource(
        name=name,
        resource_type=ResourceType.DATASET,
        location_uri=location_uri,
        **kwargs,
    )


def _make_model(
    name: str = "Test Model",
    location_uri: str = "docker://registry/model:v1",
    **kwargs,
) -> Resource:
    defaults = {
        "execution_type": ExecutionType.DOCKER,
        "io_spec": IOSpec(
            inputs=(IOSlot(name="input_data", tags=("csv",)),),
            outputs=(IOSlot(name="predictions", tags=("json",)),),
        ),
    }
    defaults.update(kwargs)
    return Resource(
        name=name,
        resource_type=ResourceType.MODEL,
        location_uri=location_uri,
        **defaults,
    )


# ── Test: Register and Retrieve ──────────────────────────────────────


class TestRegisterAndRetrieve:
    def test_register_and_get_dataset(self, pg_registry):
        r = _make_dataset(format_tags=["csv", "timeseries"], owner="alice")
        registered = pg_registry.register_resource(r)
        assert registered.id == r.id
        assert registered.name == "Test Dataset"

        retrieved = pg_registry.get_resource(r.id)
        assert retrieved.name == "Test Dataset"
        assert retrieved.resource_type == ResourceType.DATASET
        assert retrieved.format_tags == ["csv", "timeseries"]
        assert retrieved.owner == "alice"
        assert retrieved.status == ResourceStatus.ACTIVE

    def test_register_model_with_full_metadata(self, pg_registry):
        r = _make_model(
            version="2.0.0",
            authors=[
                Author(
                    name="Alice Smith",
                    orcid="0000-0001-2345-6789",
                    affiliation="NIAID VRC",
                    role="lead",
                ),
                Author(name="Bob Jones"),
            ],
            organization="NIAID VRC",
            contact_email="alice@niaid.nih.gov",
            publications=[
                Publication(title="Model Paper", doi="10.1234/test"),
            ],
            funding=["NIAID U19 AI123456"],
            organisms=["SARS-CoV-2", "Homo sapiens"],
            modeling_scales=["molecular", "cellular"],
            domains=["immunology"],
            date_published=date(2026, 1, 15),
            format_tags=["docker", "ml"],
            digest_sha256="abc123",
            size_bytes=1024000,
            external_ids={"github": "mism/model"},
            license="MIT",
            owner="team-alpha",
            metadata={"framework": "pytorch"},
        )
        pg_registry.register_resource(r)
        retrieved = pg_registry.get_resource(r.id)

        # Verify all fields round-trip correctly
        assert retrieved.version == "2.0.0"
        assert len(retrieved.authors) == 2
        assert retrieved.authors[0].name == "Alice Smith"
        assert retrieved.authors[0].orcid == "0000-0001-2345-6789"
        assert retrieved.authors[0].affiliation == "NIAID VRC"
        assert retrieved.authors[0].role == "lead"
        assert retrieved.authors[1].name == "Bob Jones"
        assert retrieved.organization == "NIAID VRC"
        assert retrieved.contact_email == "alice@niaid.nih.gov"
        assert len(retrieved.publications) == 1
        assert retrieved.publications[0].title == "Model Paper"
        assert retrieved.publications[0].doi == "10.1234/test"
        assert retrieved.funding == ["NIAID U19 AI123456"]
        assert set(retrieved.organisms) == {"SARS-CoV-2", "Homo sapiens"}
        assert set(retrieved.modeling_scales) == {"molecular", "cellular"}
        assert retrieved.domains == ["immunology"]
        assert retrieved.date_published == date(2026, 1, 15)
        assert retrieved.digest_sha256 == "abc123"
        assert retrieved.size_bytes == 1024000
        assert retrieved.external_ids["github"] == "mism/model"
        assert retrieved.license == "MIT"
        assert retrieved.metadata["framework"] == "pytorch"

    def test_get_nonexistent_raises(self, pg_registry):
        with pytest.raises(ResourceNotFoundError):
            pg_registry.get_resource("nonexistent-id")

    def test_duplicate_raises(self, pg_registry):
        r = _make_dataset()
        pg_registry.register_resource(r)
        with pytest.raises(DuplicateResourceError):
            pg_registry.register_resource(r)


# ── Test: IOSpec Round-Trip ──────────────────────────────────────────


class TestIOSpecRoundTrip:
    def test_complex_io_spec(self, pg_registry):
        spec = IOSpec(
            inputs=(
                IOSlot(name="sequences", tags=("fasta", "viral"), description="Input seqs"),
                IOSlot(name="reference", tags=("pdb",), required=False),
            ),
            outputs=(
                IOSlot(name="predictions", tags=("csv", "escape-mutations")),
                IOSlot(name="report", tags=("json",)),
            ),
            parameters_schema={"type": "object", "properties": {"threshold": {"type": "number"}}},
        )
        r = _make_model(io_spec=spec)
        pg_registry.register_resource(r)
        retrieved = pg_registry.get_resource(r.id)

        assert retrieved.io_spec is not None
        assert len(retrieved.io_spec.inputs) == 2
        assert retrieved.io_spec.inputs[0].name == "sequences"
        assert set(retrieved.io_spec.inputs[0].tags) == {"fasta", "viral"}
        assert retrieved.io_spec.inputs[0].description == "Input seqs"
        assert retrieved.io_spec.inputs[1].name == "reference"
        assert retrieved.io_spec.inputs[1].required is False
        assert len(retrieved.io_spec.outputs) == 2
        assert retrieved.io_spec.parameters_schema is not None
        assert retrieved.io_spec.parameters_schema["type"] == "object"

    def test_no_io_spec(self, pg_registry):
        r = _make_dataset()
        pg_registry.register_resource(r)
        retrieved = pg_registry.get_resource(r.id)
        assert retrieved.io_spec is None


# ── Test: Find Resources ─────────────────────────────────────────────


class TestFindResources:
    def test_find_by_type(self, pg_registry):
        pg_registry.register_resource(_make_dataset(name="D1", location_uri="s3://d1"))
        pg_registry.register_resource(_make_model(name="M1", location_uri="docker://m1"))

        datasets = pg_registry.find_resources(resource_type=ResourceType.DATASET)
        assert all(r.resource_type == ResourceType.DATASET for r in datasets)
        assert any(r.name == "D1" for r in datasets)

    def test_find_by_tags(self, pg_registry):
        pg_registry.register_resource(
            _make_dataset(name="D-csv", location_uri="s3://d-csv", format_tags=["csv", "viral"])
        )
        pg_registry.register_resource(
            _make_dataset(name="D-fasta", location_uri="s3://d-fasta", format_tags=["fasta"])
        )
        results = pg_registry.find_resources(tags=["csv"])
        assert any(r.name == "D-csv" for r in results)
        assert not any(r.name == "D-fasta" for r in results)

    def test_find_by_organisms(self, pg_registry):
        pg_registry.register_resource(
            _make_dataset(
                name="D-sars", location_uri="s3://d-sars", organisms=["SARS-CoV-2"]
            )
        )
        pg_registry.register_resource(
            _make_dataset(name="D-human", location_uri="s3://d-human", organisms=["Homo sapiens"])
        )
        results = pg_registry.find_resources(organisms=["SARS-CoV-2"])
        assert any(r.name == "D-sars" for r in results)
        assert not any(r.name == "D-human" for r in results)

    def test_find_by_scales(self, pg_registry):
        pg_registry.register_resource(
            _make_dataset(
                name="D-mol",
                location_uri="s3://d-mol",
                modeling_scales=["molecular"],
            )
        )
        results = pg_registry.find_resources(scales=["molecular"])
        assert any(r.name == "D-mol" for r in results)

    def test_find_by_name_contains(self, pg_registry):
        pg_registry.register_resource(
            _make_dataset(name="Spike Protein Data", location_uri="s3://spike")
        )
        pg_registry.register_resource(
            _make_dataset(name="Gene Expression", location_uri="s3://gene")
        )
        results = pg_registry.find_resources(name_contains="spike")
        assert any(r.name == "Spike Protein Data" for r in results)
        assert not any(r.name == "Gene Expression" for r in results)

    def test_find_by_owner(self, pg_registry):
        pg_registry.register_resource(
            _make_dataset(name="D-alice", location_uri="s3://d-alice", owner="alice")
        )
        pg_registry.register_resource(
            _make_dataset(name="D-bob", location_uri="s3://d-bob", owner="bob")
        )
        results = pg_registry.find_resources(owner="alice")
        assert any(r.name == "D-alice" for r in results)
        assert not any(r.name == "D-bob" for r in results)

    def test_find_no_matches(self, pg_registry):
        results = pg_registry.find_resources(tags=["nonexistent-tag-xyz"])
        assert results == []


# ── Test: Update Resource ────────────────────────────────────────────


class TestUpdateResource:
    def test_metadata_correction(self, pg_registry):
        r = _make_dataset(description="Old desc")
        pg_registry.register_resource(r)

        r.description = "New desc"
        r.format_tags = ["csv", "updated"]
        r.updated_at = datetime.now(timezone.utc)
        updated = pg_registry.update_resource(r)

        assert updated.description == "New desc"
        assert "updated" in updated.format_tags

        # Verify persistence
        retrieved = pg_registry.get_resource(r.id)
        assert retrieved.description == "New desc"

    def test_update_nonexistent_raises(self, pg_registry):
        r = _make_dataset()
        r.id = "nonexistent-id"
        with pytest.raises(ResourceNotFoundError):
            pg_registry.update_resource(r)


# ── Test: Run CRUD ───────────────────────────────────────────────────


class TestRunCRUD:
    def test_create_and_get_run(self, pg_registry):
        model = _make_model()
        pg_registry.register_resource(model)
        dataset = _make_dataset()
        pg_registry.register_resource(dataset)

        run = Run(
            model_id=model.id,
            model_version="1.0.0",
            input_resource_ids=[dataset.id],
            parameters={"threshold": 0.5, "batch_size": 32},
            environment=RunEnvironment(
                platform="helx",
                hardware_description="4xA100",
                extra={"gpu_count": 4},
            ),
            triggered_by="researcher@niaid.nih.gov",
            notes="Test run",
        )
        created = pg_registry.create_run(run)
        assert created.id == run.id
        assert created.status == RunStatus.REGISTERED

        retrieved = pg_registry.get_run(run.id)
        assert retrieved.model_id == model.id
        assert retrieved.model_version == "1.0.0"
        assert retrieved.input_resource_ids == [dataset.id]
        assert retrieved.parameters["threshold"] == 0.5
        assert retrieved.parameters["batch_size"] == 32
        assert retrieved.environment is not None
        assert retrieved.environment.platform == "helx"
        assert retrieved.environment.hardware_description == "4xA100"
        assert retrieved.environment.extra["gpu_count"] == 4
        assert retrieved.triggered_by == "researcher@niaid.nih.gov"
        assert retrieved.notes == "Test run"

    def test_get_run_nonexistent_raises(self, pg_registry):
        with pytest.raises(RunNotFoundError):
            pg_registry.get_run("nonexistent-run-id")

    def test_update_run(self, pg_registry):
        model = _make_model(name="M-update", location_uri="docker://m-update")
        pg_registry.register_resource(model)

        run = Run(model_id=model.id)
        pg_registry.create_run(run)

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        updated = pg_registry.update_run(run)
        assert updated.status == RunStatus.RUNNING
        assert updated.started_at is not None


# ── Test: Find Runs ──────────────────────────────────────────────────


class TestFindRuns:
    def test_find_by_model_id(self, pg_registry):
        m1 = _make_model(name="M-find1", location_uri="docker://m-find1")
        m2 = _make_model(name="M-find2", location_uri="docker://m-find2")
        pg_registry.register_resource(m1)
        pg_registry.register_resource(m2)

        pg_registry.create_run(Run(model_id=m1.id))
        pg_registry.create_run(Run(model_id=m2.id))

        results = pg_registry.find_runs(model_id=m1.id)
        assert len(results) == 1
        assert results[0].model_id == m1.id

    def test_find_by_input_resource_id(self, pg_registry):
        model = _make_model(name="M-input", location_uri="docker://m-input")
        d1 = _make_dataset(name="D-input1", location_uri="s3://d-input1")
        d2 = _make_dataset(name="D-input2", location_uri="s3://d-input2")
        pg_registry.register_resource(model)
        pg_registry.register_resource(d1)
        pg_registry.register_resource(d2)

        pg_registry.create_run(Run(model_id=model.id, input_resource_ids=[d1.id]))
        pg_registry.create_run(Run(model_id=model.id, input_resource_ids=[d2.id]))

        results = pg_registry.find_runs(input_resource_id=d1.id)
        assert len(results) == 1
        assert d1.id in results[0].input_resource_ids

    def test_find_by_status(self, pg_registry):
        model = _make_model(name="M-status", location_uri="docker://m-status")
        pg_registry.register_resource(model)

        run = Run(model_id=model.id, status=RunStatus.REGISTERED)
        pg_registry.create_run(run)

        results = pg_registry.find_runs(status=RunStatus.REGISTERED)
        assert any(r.id == run.id for r in results)

        results = pg_registry.find_runs(status=RunStatus.COMPLETED)
        assert not any(r.id == run.id for r in results)


# ── Test: Lineage ────────────────────────────────────────────────────


class TestLineage:
    def test_get_lineage(self, pg_registry):
        model = _make_model(name="M-lineage", location_uri="docker://m-lineage")
        d_in = _make_dataset(name="D-in", location_uri="s3://d-in")
        pg_registry.register_resource(model)
        pg_registry.register_resource(d_in)

        d_out = _make_dataset(name="D-out", location_uri="s3://d-out")
        pg_registry.register_resource(d_out)

        run = Run(
            model_id=model.id,
            input_resource_ids=[d_in.id],
            output_resource_ids=[d_out.id],
            status=RunStatus.COMPLETED,
        )
        pg_registry.create_run(run)

        lineage = pg_registry.get_lineage(d_out.id)
        assert len(lineage) == 1
        assert lineage[0].model_id == model.id

    def test_get_dependents(self, pg_registry):
        model = _make_model(name="M-deps", location_uri="docker://m-deps")
        d_in = _make_dataset(name="D-dep-in", location_uri="s3://d-dep-in")
        pg_registry.register_resource(model)
        pg_registry.register_resource(d_in)

        run = Run(
            model_id=model.id,
            input_resource_ids=[d_in.id],
        )
        pg_registry.create_run(run)

        deps = pg_registry.get_dependents(d_in.id)
        assert len(deps) == 1
        assert deps[0].model_id == model.id

    def test_no_lineage(self, pg_registry):
        d = _make_dataset(name="D-orphan", location_uri="s3://d-orphan")
        pg_registry.register_resource(d)
        assert pg_registry.get_lineage(d.id) == []

    def test_no_dependents(self, pg_registry):
        d = _make_dataset(name="D-leaf", location_uri="s3://d-leaf")
        pg_registry.register_resource(d)
        assert pg_registry.get_dependents(d.id) == []


# ── Test: Versioning ─────────────────────────────────────────────────


class TestVersioning:
    def test_get_latest_version_single(self, pg_registry):
        r = _make_dataset(name="D-v1", location_uri="s3://d-v1")
        pg_registry.register_resource(r)

        latest = pg_registry.get_latest_version(r.id)
        assert latest is not None
        assert latest.id == r.id

    def test_get_latest_version_chain(self, pg_registry):
        v1 = _make_dataset(name="D-chain", location_uri="s3://chain-v1")
        pg_registry.register_resource(v1)

        v2 = _make_dataset(
            name="D-chain", location_uri="s3://chain-v2", new_version_of=v1.id
        )
        pg_registry.register_resource(v2)

        # Mark v1 as superseded
        v1.status = ResourceStatus.SUPERSEDED
        v1.superseded_by = v2.id
        v1.updated_at = datetime.now(timezone.utc)
        pg_registry.update_resource(v1)

        latest = pg_registry.get_latest_version(v1.id)
        assert latest is not None
        assert latest.id == v2.id

    def test_get_latest_version_nonexistent(self, pg_registry):
        assert pg_registry.get_latest_version("nonexistent-id") is None

    def test_get_version_history(self, pg_registry):
        v1 = _make_dataset(name="D-hist", location_uri="s3://hist-v1")
        pg_registry.register_resource(v1)

        v2 = _make_dataset(
            name="D-hist", location_uri="s3://hist-v2", new_version_of=v1.id
        )
        pg_registry.register_resource(v2)

        v3 = _make_dataset(
            name="D-hist", location_uri="s3://hist-v3", new_version_of=v2.id
        )
        pg_registry.register_resource(v3)

        # Wire up the superseded_by pointers
        v1.status = ResourceStatus.SUPERSEDED
        v1.superseded_by = v2.id
        v1.updated_at = datetime.now(timezone.utc)
        pg_registry.update_resource(v1)

        v2.status = ResourceStatus.SUPERSEDED
        v2.superseded_by = v3.id
        v2.updated_at = datetime.now(timezone.utc)
        pg_registry.update_resource(v2)

        # Query from any point in the chain
        for rid in [v1.id, v2.id, v3.id]:
            history = pg_registry.get_version_history(rid)
            assert len(history) == 3
            assert history[0].id == v1.id
            assert history[1].id == v2.id
            assert history[2].id == v3.id

    def test_get_version_history_nonexistent(self, pg_registry):
        assert pg_registry.get_version_history("nonexistent-id") == []
