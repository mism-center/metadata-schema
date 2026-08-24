"""Integration tests for PostgresRegistry backend.

Requires a running Postgres instance. Set MISM_TEST_DATABASE_URL to enable:

    export MISM_TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/mism_test
    uv run pytest tests/test_postgres_backend.py -v

The pg_engine fixture applies Alembic migrations programmatically, so the
entire suite also validates that the migration-managed schema is correct.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from mism_registry import (
    Author,
    ExecutionType,
    ImageReviewStatus,
    IOSlot,
    IOSpec,
    Publication,
    Resource,
    ResourceType,
    ResourceVersionStatus,
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

    # Wipe any previous test state cleanly
    Base.metadata.drop_all(engine)
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        conn.execute(
            text("DROP TYPE IF EXISTS resourcetype, executiontype, resourcestatus, runstatus")
        )
        conn.commit()

    # Apply all migrations — tests run against the Alembic-managed schema,
    # so this suite also validates that migrations produce a working database.
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    yield engine
    engine.dispose()


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
        assert retrieved.version_status == ResourceVersionStatus.ACTIVE

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
            model_scales=["molecular", "cellular"],
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
        assert set(retrieved.model_scales) == {"molecular", "cellular"}
        assert retrieved.domains == ["immunology"]
        assert retrieved.date_published == date(2026, 1, 15)
        assert retrieved.digest_sha256 == "abc123"
        assert retrieved.size_bytes == 1024000
        assert retrieved.external_ids["github"] == "mism/model"
        assert retrieved.license == "MIT"
        assert retrieved.metadata["framework"] == "pytorch"

    def test_register_model_with_annotation_fields(self, pg_registry):
        """schema.md Section A/B/C fields survive a full DB round-trip."""
        from mism_registry.types import (
            Argument,
            Compute,
            Contact,
            Container,
            DataInput,
            Dependency,
            EntryPoint,
            ExperimentProtocol,
            IODetail,
            Output,
            Parameter,
            RelatedResource,
            TestSpec,
        )

        r = _make_model(
            execution_type=ExecutionType.SINGULARITY,
            short_description="short",
            model_class=["agent-based model"],
            formalism=["ODE"],
            determinism="stochastic",
            time_dynamics="continuous",
            spatial="lattice",
            multiscale=True,
            infectious_agents=["SARS-CoV-2"],
            health_conditions=["COVID-19"],
            biological_processes=["viral entry"],
            molecular_entities=["ATP"],
            proteins_genes=["ACE2"],
            contacts=[Contact(name="Carol", role="maintainer", email="c@x.org")],
            related_resources=[
                RelatedResource(qualifier="bqmodel:isDerivedFrom", scheme="doi", value="10.9")
            ],
            execution_status="characterized",
            language_name="Python",
            language_version=">=3.10",
            execution_notes="note",
            dependencies=[Dependency(name="numpy", version_constraint=">=1.24")],
            containers=[Container(kind="docker", file="Dockerfile")],
            compute=Compute(cpu_cores=8, gpu_required=False, parallelism="MPI"),
            entry_points=[
                EntryPoint(
                    command="python run.py",
                    purpose="main",
                    arguments=(Argument(name="--dur", default=10.0),),
                )
            ],
            tests=TestSpec(framework="pytest", invocation="pytest tests/"),
            io=IODetail(
                parameters=(Parameter(name="k_run", default_value=1.0, unit="per second"),),
                data_inputs=(DataInput(name="field.csv", format="CSV", required=True),),
                outputs=(Output(name="traj", unit="m", format="CSV"),),
                experiment_protocol=ExperimentProtocol(
                    duration=10.0, duration_unit="s", observables=("x", "y")
                ),
            ),
        )
        pg_registry.register_resource(r)
        got = pg_registry.get_resource(r.id)

        assert got == r  # full-fidelity round-trip

    def test_get_nonexistent_raises(self, pg_registry):
        with pytest.raises(ResourceNotFoundError):
            pg_registry.get_resource("nonexistent-id")

    def test_duplicate_raises(self, pg_registry):
        r = _make_dataset()
        pg_registry.register_resource(r)
        with pytest.raises(DuplicateResourceError):
            pg_registry.register_resource(r)

    def test_image_review_defaults_round_trip(self, pg_registry):
        """A freshly registered model has no image review state yet (MISM-291)."""
        r = _make_model()
        pg_registry.register_resource(r)
        retrieved = pg_registry.get_resource(r.id)

        assert retrieved.image_review_status == ImageReviewStatus.NOT_APPLICABLE
        assert retrieved.image_reviewed_by == ""
        assert retrieved.image_reviewed_at is None
        assert retrieved.image_rejection_reason == ""
        assert retrieved.metadata_reviewed_by == ""
        assert retrieved.metadata_reviewed_at is None
        assert retrieved.metadata_rejection_reason == ""


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
            _make_dataset(name="D-sars", location_uri="s3://d-sars", organisms=["SARS-CoV-2"])
        )
        pg_registry.register_resource(
            _make_dataset(name="D-human", location_uri="s3://d-human", organisms=["Homo sapiens"])
        )
        results = pg_registry.find_resources(organisms=["SARS-CoV-2"])
        assert any(r.name == "D-sars" for r in results)
        assert not any(r.name == "D-human" for r in results)

    def test_find_by_scales(self, pg_registry):
        pg_registry.register_resource(
            _make_dataset(name="D-mol", location_uri="s3://d-mol", model_scales=["molecular"])
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

    def test_find_all_no_filters(self, pg_registry):
        pg_registry.register_resource(_make_dataset(name="DA-all", location_uri="s3://da-all"))
        pg_registry.register_resource(_make_model(name="MA-all", location_uri="docker://ma-all"))
        results = pg_registry.find_resources()
        names = {r.name for r in results}
        assert "DA-all" in names
        assert "MA-all" in names

    def test_find_combined_filters(self, pg_registry):
        """AND logic: resource must satisfy type + tags + owner simultaneously."""
        pg_registry.register_resource(
            _make_dataset(
                name="D-combo-match",
                location_uri="s3://combo-match",
                format_tags=["csv", "genomics"],
                owner="combo-owner",
            )
        )
        # Same type + owner but wrong tags
        pg_registry.register_resource(
            _make_dataset(
                name="D-combo-wrong-tag",
                location_uri="s3://combo-wrong-tag",
                format_tags=["fasta"],
                owner="combo-owner",
            )
        )
        # Same type + tags but different owner
        pg_registry.register_resource(
            _make_dataset(
                name="D-combo-wrong-owner",
                location_uri="s3://combo-wrong-owner",
                format_tags=["csv", "genomics"],
                owner="other-owner",
            )
        )

        results = pg_registry.find_resources(
            resource_type=ResourceType.DATASET,
            tags=["csv"],
            owner="combo-owner",
        )
        names = {r.name for r in results}
        assert "D-combo-match" in names
        assert "D-combo-wrong-tag" not in names
        assert "D-combo-wrong-owner" not in names


# ── Test: Search Resources (structured filters) ──────────────────────


class TestSearchResourcesImageReviewFilter:
    """Exercises search_resources() end-to-end for image_review_status —
    the actual query path a future 'pending image review' endpoint depends
    on, not just the static FILTERABLE_FIELDS/_FILTER_COLUMN_MAP consistency
    checked in test_search_fields.py."""

    def test_filters_by_pending_image_check(self, pg_registry):
        from mism_registry.search import FieldFilter, SearchQuery

        pending = _make_model(name="Pending Model", location_uri="docker://pending")
        pending.image_review_status = ImageReviewStatus.PENDING_IMAGE_CHECK
        pg_registry.register_resource(pending)

        approved = _make_model(name="Approved Model", location_uri="docker://approved")
        approved.image_review_status = ImageReviewStatus.IMAGE_APPROVED
        pg_registry.register_resource(approved)

        result = pg_registry.search_resources(
            SearchQuery(
                filters=(
                    FieldFilter(field="image_review_status", op="eq", value="pending_image_check"),
                ),
            )
        )

        names = {r.name for r in result.resources}
        assert names == {"Pending Model"}
        assert result.total == 1

    def test_aggregates_by_image_review_status(self, pg_registry):
        from mism_registry.search import FieldFilter, SearchQuery

        for status in (
            ImageReviewStatus.PENDING_IMAGE_CHECK,
            ImageReviewStatus.PENDING_IMAGE_CHECK,
            ImageReviewStatus.IMAGE_APPROVED,
        ):
            m = _make_model(name=f"Model-{status.value}-{id(object())}")
            m.image_review_status = status
            pg_registry.register_resource(m)

        result = pg_registry.search_resources(
            SearchQuery(
                filters=(FieldFilter(field="resource_type", op="eq", value="model"),),
                agg_fields=("image_review_status",),
            )
        )

        buckets = {b.key: b.count for b in result.aggs["image_review_status"]}
        assert buckets.get("pending_image_check") == 2
        assert buckets.get("image_approved") == 1


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

        retrieved = pg_registry.get_resource(r.id)
        assert retrieved.description == "New desc"

    def test_update_nonexistent_raises(self, pg_registry):
        r = _make_dataset()
        r.id = "nonexistent-id"
        with pytest.raises(ResourceNotFoundError):
            pg_registry.update_resource(r)

    def test_image_review_fields_round_trip_through_update(self, pg_registry):
        """update_resource() has its own manual field-by-field mapping (distinct
        from resource_to_db) — this guards against the review fields being
        silently dropped there, the way containers/image_name etc. already are."""
        from mism_registry.types import Container

        r = _make_model(containers=[Container(kind="docker", image_name="model:v1")])
        pg_registry.register_resource(r)

        r.image_review_status = ImageReviewStatus.IMAGE_APPROVED
        r.image_reviewed_by = "frank"
        r.image_reviewed_at = datetime.now(timezone.utc)
        r.image_rejection_reason = ""
        r.metadata_reviewed_by = "erin"
        r.metadata_reviewed_at = datetime.now(timezone.utc)
        r.metadata_rejection_reason = "minor fix requested"
        pg_registry.update_resource(r)

        retrieved = pg_registry.get_resource(r.id)
        assert retrieved.image_review_status == ImageReviewStatus.IMAGE_APPROVED
        assert retrieved.image_reviewed_by == "frank"
        assert retrieved.image_reviewed_at is not None
        assert retrieved.metadata_reviewed_by == "erin"
        assert retrieved.metadata_reviewed_at is not None
        assert retrieved.metadata_rejection_reason == "minor fix requested"


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

    def test_update_run_nonexistent_raises(self, pg_registry):
        run = Run(model_id="any-model")
        run.id = "nonexistent-run-id"
        with pytest.raises(RunNotFoundError):
            pg_registry.update_run(run)

    def test_run_completed_fields(self, pg_registry):
        """output_resource_ids, completed_at persist after COMPLETED update."""
        model = _make_model(name="M-complete", location_uri="docker://m-complete")
        d_in = _make_dataset(name="D-comp-in", location_uri="s3://d-comp-in")
        d_out = _make_dataset(name="D-comp-out", location_uri="s3://d-comp-out")
        pg_registry.register_resource(model)
        pg_registry.register_resource(d_in)
        pg_registry.register_resource(d_out)

        run = Run(model_id=model.id, input_resource_ids=[d_in.id])
        pg_registry.create_run(run)

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        pg_registry.update_run(run)

        run.status = RunStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        run.output_resource_ids = [d_out.id]
        pg_registry.update_run(run)

        retrieved = pg_registry.get_run(run.id)
        assert retrieved.status == RunStatus.COMPLETED
        assert retrieved.completed_at is not None
        assert retrieved.output_resource_ids == [d_out.id]

    def test_run_failed_fields(self, pg_registry):
        """error_message, log_uri, completed_at persist after FAILED update."""
        model = _make_model(name="M-fail", location_uri="docker://m-fail")
        pg_registry.register_resource(model)

        run = Run(model_id=model.id)
        pg_registry.create_run(run)

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        pg_registry.update_run(run)

        run.status = RunStatus.FAILED
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = "OOM killed on node gpu-03"
        run.log_uri = "s3://mism-logs/run-abc/stderr.log"
        pg_registry.update_run(run)

        retrieved = pg_registry.get_run(run.id)
        assert retrieved.status == RunStatus.FAILED
        assert retrieved.error_message == "OOM killed on node gpu-03"
        assert retrieved.log_uri == "s3://mism-logs/run-abc/stderr.log"
        assert retrieved.completed_at is not None


# ── Test: RunEnvironment Round-Trip ──────────────────────────────────


class TestRunEnvironment:
    def test_all_fields_round_trip(self, pg_registry):
        """Every RunEnvironment field survives the JSONB round-trip."""
        model = _make_model(name="M-env", location_uri="docker://m-env")
        pg_registry.register_resource(model)

        env = RunEnvironment(
            platform="biowulf",
            container_uri="docker://mism/escape-model:v2.0",
            container_digest="sha256:abc123def456",
            conda_env="environment.yml",
            hardware_description="2x V100 32GB",
            extra={"slurm_job_id": 12345, "partition": "gpu"},
        )
        run = Run(model_id=model.id, environment=env)
        pg_registry.create_run(run)

        retrieved = pg_registry.get_run(run.id)
        assert retrieved.environment is not None
        e = retrieved.environment
        assert e.platform == "biowulf"
        assert e.container_uri == "docker://mism/escape-model:v2.0"
        assert e.container_digest == "sha256:abc123def456"
        assert e.conda_env == "environment.yml"
        assert e.hardware_description == "2x V100 32GB"
        assert e.extra["slurm_job_id"] == 12345
        assert e.extra["partition"] == "gpu"

    def test_no_environment(self, pg_registry):
        """Run created without an environment comes back with environment=None."""
        model = _make_model(name="M-no-env", location_uri="docker://m-no-env")
        pg_registry.register_resource(model)

        run = Run(model_id=model.id)
        pg_registry.create_run(run)

        retrieved = pg_registry.get_run(run.id)
        assert retrieved.environment is None


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

    def test_find_combined_model_and_status(self, pg_registry):
        """model_id + status together: AND logic."""
        m = _make_model(name="M-combo-run", location_uri="docker://m-combo-run")
        pg_registry.register_resource(m)

        run_reg = Run(model_id=m.id, status=RunStatus.REGISTERED)
        run_fail = Run(model_id=m.id, status=RunStatus.FAILED)
        pg_registry.create_run(run_reg)
        pg_registry.create_run(run_fail)

        results = pg_registry.find_runs(model_id=m.id, status=RunStatus.REGISTERED)
        assert len(results) == 1
        assert results[0].id == run_reg.id

    def test_find_by_triggered_by(self, pg_registry):
        model = _make_model(name="M-trig", location_uri="docker://m-trig")
        pg_registry.register_resource(model)

        mine = Run(model_id=model.id, triggered_by="user-1")
        theirs = Run(model_id=model.id, triggered_by="user-2")
        pg_registry.create_run(mine)
        pg_registry.create_run(theirs)

        results = pg_registry.find_runs(triggered_by="user-1")
        assert [r.id for r in results] == [mine.id]

    def test_find_combined_triggered_by_and_status(self, pg_registry):
        """triggered_by + status together: AND logic."""
        model = _make_model(name="M-trig-combo", location_uri="docker://m-trig-combo")
        pg_registry.register_resource(model)

        mine_running = Run(model_id=model.id, triggered_by="user-1", status=RunStatus.RUNNING)
        mine_done = Run(model_id=model.id, triggered_by="user-1", status=RunStatus.COMPLETED)
        theirs_running = Run(model_id=model.id, triggered_by="user-2", status=RunStatus.RUNNING)
        pg_registry.create_run(mine_running)
        pg_registry.create_run(mine_done)
        pg_registry.create_run(theirs_running)

        results = pg_registry.find_runs(triggered_by="user-1", status=RunStatus.RUNNING)
        assert [r.id for r in results] == [mine_running.id]

    def test_find_no_matches(self, pg_registry):
        results = pg_registry.find_runs(model_id="nonexistent-model-id-xyz")
        assert results == []


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

        run = Run(model_id=model.id, input_resource_ids=[d_in.id])
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

        v2 = _make_dataset(name="D-chain", location_uri="s3://chain-v2", new_version_of=v1.id)
        pg_registry.register_resource(v2)

        v1.version_status = ResourceVersionStatus.SUPERSEDED
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

        v2 = _make_dataset(name="D-hist", location_uri="s3://hist-v2", new_version_of=v1.id)
        pg_registry.register_resource(v2)

        v3 = _make_dataset(name="D-hist", location_uri="s3://hist-v3", new_version_of=v2.id)
        pg_registry.register_resource(v3)

        v1.version_status = ResourceVersionStatus.SUPERSEDED
        v1.superseded_by = v2.id
        v1.updated_at = datetime.now(timezone.utc)
        pg_registry.update_resource(v1)

        v2.version_status = ResourceVersionStatus.SUPERSEDED
        v2.superseded_by = v3.id
        v2.updated_at = datetime.now(timezone.utc)
        pg_registry.update_resource(v2)

        # Chain navigable from any point
        for rid in [v1.id, v2.id, v3.id]:
            history = pg_registry.get_version_history(rid)
            assert len(history) == 3
            assert history[0].id == v1.id
            assert history[1].id == v2.id
            assert history[2].id == v3.id

    def test_get_version_history_nonexistent(self, pg_registry):
        assert pg_registry.get_version_history("nonexistent-id") == []


# ── Test: Edge Cases ─────────────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_in_fields(self, pg_registry):
        """Unicode characters in name, description, and notes survive round-trips."""
        r = _make_dataset(
            name="SARS-CoV-2 Αλφα παραλλαγή",  # Greek
            location_uri="s3://unicode-test/data.csv",
            description="Données génomiques du variant 日本語 テスト",  # French + Japanese
        )
        pg_registry.register_resource(r)
        retrieved = pg_registry.get_resource(r.id)
        assert retrieved.name == "SARS-CoV-2 Αλφα παραλλαγή"
        assert "génomiques" in retrieved.description

        model = _make_model(name="M-unicode", location_uri="docker://m-unicode")
        pg_registry.register_resource(model)
        run = Run(model_id=model.id, notes="Запуск с параметрами 中文")  # Russian + Chinese
        pg_registry.create_run(run)
        ret_run = pg_registry.get_run(run.id)
        assert "параметрами" in ret_run.notes

    def test_execution_ref_round_trip(self, pg_registry):
        """execution_ref (git hash, image tag, etc.) is stored and retrieved."""
        r = _make_model(
            name="M-execref",
            location_uri="docker://mism/model:v3",
            execution_ref="git+https://github.com/mism/model@a1b2c3d4",
        )
        pg_registry.register_resource(r)
        retrieved = pg_registry.get_resource(r.id)
        assert retrieved.execution_ref == "git+https://github.com/mism/model@a1b2c3d4"

    def test_large_metadata(self, pg_registry):
        """Deeply nested metadata dict round-trips correctly via JSONB."""
        large_meta = {
            "training": {
                "epochs": 100,
                "learning_rate": 0.001,
                "optimizer": "adam",
                "scheduler": {"type": "cosine", "T_max": 50},
            },
            "data": {
                "train_split": 0.8,
                "val_split": 0.1,
                "test_split": 0.1,
                "augmentations": ["random_crop", "horizontal_flip", "color_jitter"],
            },
            "hardware": {
                "gpus": 4,
                "gpu_type": "A100",
                "memory_gb": 320,
                "nodes": 1,
            },
            "tags": ["production", "v3", "validated"],
            "checksum": "sha256:deadbeef",
        }
        r = _make_dataset(
            name="D-large-meta",
            location_uri="s3://large-meta/data.csv",
            metadata=large_meta,
        )
        pg_registry.register_resource(r)
        retrieved = pg_registry.get_resource(r.id)

        assert retrieved.metadata["training"]["epochs"] == 100
        assert retrieved.metadata["training"]["scheduler"]["type"] == "cosine"
        assert retrieved.metadata["data"]["augmentations"] == [
            "random_crop",
            "horizontal_flip",
            "color_jitter",
        ]
        assert retrieved.metadata["hardware"]["gpus"] == 4
        assert "production" in retrieved.metadata["tags"]

    def test_resource_archived_status(self, pg_registry):
        """ARCHIVED status is stored and retrieved correctly."""
        r = _make_dataset(
            name="D-archived",
            location_uri="s3://archived/old-data.csv",
            version_status=ResourceVersionStatus.ARCHIVED,
        )
        pg_registry.register_resource(r)
        retrieved = pg_registry.get_resource(r.id)
        assert retrieved.version_status == ResourceVersionStatus.ARCHIVED

        # Also verify it's not returned as ACTIVE in a status-implied search
        # (find_resources has no status filter, but we can confirm the field)
        all_resources = pg_registry.find_resources()
        match = next((x for x in all_resources if x.id == r.id), None)
        assert match is not None
        assert match.version_status == ResourceVersionStatus.ARCHIVED


# ── Test: Get Model Run Details ─────────────────────────────────────


class TestGetModelRunDetails:
    def test_completed_run_with_outputs(self, pg_registry):
        """Full lifecycle: model + dataset → run → complete with output → detail query."""
        model = _make_model(name="M-detail", location_uri="docker://m-detail:v1")
        pg_registry.register_resource(model)
        d_in = _make_dataset(name="D-in-detail", location_uri="s3://detail-in")
        pg_registry.register_resource(d_in)
        d_out = _make_dataset(name="D-out-detail", location_uri="s3://detail-out")
        pg_registry.register_resource(d_out)

        run = Run(
            model_id=model.id,
            model_version="1.0",
            input_resource_ids=[d_in.id],
            output_resource_ids=[d_out.id],
            status=RunStatus.COMPLETED,
        )
        pg_registry.create_run(run)

        summary = pg_registry.get_model_run_details(model.id)
        assert summary.model.id == model.id
        assert summary.model.name == "M-detail"
        assert len(summary.runs) == 1

        detail = summary.runs[0]
        assert detail.run.model_id == model.id
        assert detail.run.status == RunStatus.COMPLETED
        assert len(detail.input_resources) == 1
        assert detail.input_resources[0].id == d_in.id
        assert detail.input_resources[0].name == "D-in-detail"
        assert len(detail.output_resources) == 1
        assert detail.output_resources[0].id == d_out.id
        assert detail.output_resources[0].name == "D-out-detail"

    def test_no_runs_returns_empty(self, pg_registry):
        model = _make_model(name="M-empty-runs", location_uri="docker://m-empty:v1")
        pg_registry.register_resource(model)

        summary = pg_registry.get_model_run_details(model.id)
        assert summary.model.id == model.id
        assert summary.runs == []

    def test_multiple_runs(self, pg_registry):
        model = _make_model(name="M-multi-runs", location_uri="docker://m-multi:v1")
        pg_registry.register_resource(model)
        d_in = _make_dataset(name="D-multi-in", location_uri="s3://multi-in")
        pg_registry.register_resource(d_in)

        run1 = Run(model_id=model.id, input_resource_ids=[d_in.id])
        run2 = Run(model_id=model.id, input_resource_ids=[d_in.id])
        pg_registry.create_run(run1)
        pg_registry.create_run(run2)

        summary = pg_registry.get_model_run_details(model.id)
        assert len(summary.runs) == 2

    def test_filter_by_status(self, pg_registry):
        model = _make_model(name="M-status-filter", location_uri="docker://m-sf:v1")
        pg_registry.register_resource(model)

        run_reg = Run(model_id=model.id, status=RunStatus.REGISTERED)
        run_run = Run(model_id=model.id, status=RunStatus.RUNNING)
        pg_registry.create_run(run_reg)
        pg_registry.create_run(run_run)

        summary = pg_registry.get_model_run_details(model.id, status=RunStatus.RUNNING)
        assert len(summary.runs) == 1
        assert summary.runs[0].run.status == RunStatus.RUNNING

    def test_nonexistent_model_raises(self, pg_registry):
        with pytest.raises(ResourceNotFoundError):
            pg_registry.get_model_run_details("nonexistent-id")

    def test_shared_input_across_runs(self, pg_registry):
        """Two runs sharing the same input → resource fetched once, both hydrated."""
        model = _make_model(name="M-shared", location_uri="docker://m-shared:v1")
        pg_registry.register_resource(model)
        shared_ds = _make_dataset(name="D-shared", location_uri="s3://shared")
        pg_registry.register_resource(shared_ds)

        pg_registry.create_run(Run(model_id=model.id, input_resource_ids=[shared_ds.id]))
        pg_registry.create_run(Run(model_id=model.id, input_resource_ids=[shared_ds.id]))

        summary = pg_registry.get_model_run_details(model.id)
        assert len(summary.runs) == 2
        assert summary.runs[0].input_resources[0].id == shared_ds.id
        assert summary.runs[1].input_resources[0].id == shared_ds.id

    def test_run_with_no_outputs(self, pg_registry):
        model = _make_model(name="M-no-out", location_uri="docker://m-no-out:v1")
        pg_registry.register_resource(model)

        pg_registry.create_run(Run(model_id=model.id))

        summary = pg_registry.get_model_run_details(model.id)
        assert len(summary.runs) == 1
        assert summary.runs[0].output_resources == []
        assert summary.runs[0].input_resources == []
