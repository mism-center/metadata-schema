"""PostgresRegistry — SQLAlchemy/psycopg3 implementation of the Registry protocol.

Requires: pip install mism-registry[postgres]

Usage::

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from mism_registry.backends.postgres import Base, PostgresRegistry

    engine = create_engine("postgresql+psycopg://user:pass@localhost/mism")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        registry = PostgresRegistry(session)
        # use with any mism_registry operation function
        session.commit()
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    create_engine,
    func,
    literal_column,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

from mism_registry.enums import ExecutionType, ResourceStatus, ResourceType, RunStatus
from mism_registry.errors import (
    DuplicateResourceError,
    ResourceNotFoundError,
    RunNotFoundError,
)
from mism_registry.resource import Resource
from mism_registry.run import Run
from mism_registry.run_detail import ModelRunDetail, ModelRunSummary
from mism_registry.search import SearchQuery, SearchResult
from mism_registry.types import Author, IOSlot, IOSpec, Publication, RunEnvironment

# ── SQLAlchemy Base ──────────────────────────────────────────────────


def _enum_values(e: Any) -> list[str]:
    return [x.value for x in e]


class Base(DeclarativeBase):
    """Shared declarative base for all MISM registry models."""


# ── Table Models ─────────────────────────────────────────────────────


class ResourceModel(Base):
    """SQLAlchemy model for the ``resources`` table."""

    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(ResourceType, values_callable=_enum_values, name="resourcetype", create_type=False),
    )
    location_uri: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[ResourceStatus] = mapped_column(
        Enum(
            ResourceStatus,
            values_callable=_enum_values,
            name="resourcestatus",
            create_type=False,
        ),
        default=ResourceStatus.ACTIVE,
    )
    new_version_of: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("resources.id"),
        nullable=True,
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("resources.id"),
        nullable=True,
    )

    # Authorship & attribution
    authors: Mapped[Any] = mapped_column(JSONB, default=list)
    organization: Mapped[str] = mapped_column(String(500), default="")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    publications: Mapped[Any] = mapped_column(JSONB, default=list)
    funding: Mapped[Any] = mapped_column(JSONB, default=list)

    # Scientific context
    modeling_scales: Mapped[list] = mapped_column(ARRAY(String), default=list)
    organisms: Mapped[list] = mapped_column(ARRAY(String), default=list)
    domains: Mapped[list] = mapped_column(ARRAY(String), default=list)
    date_published: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Location & integrity
    format_tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    digest_sha256: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    external_ids: Mapped[Any] = mapped_column(JSONB, default=dict)
    license: Mapped[str] = mapped_column(String(100), default="")

    # Execution (model/tool only)
    execution_type: Mapped[ExecutionType | None] = mapped_column(
        Enum(ExecutionType, values_callable=_enum_values, name="executiontype", create_type=False),
        nullable=True,
    )
    execution_ref: Mapped[str] = mapped_column(Text, default="")
    io_spec: Mapped[Any] = mapped_column(JSONB, nullable=True)

    # System
    owner: Mapped[str] = mapped_column(String(255), default="")
    metadata_: Mapped[Any] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Full-text search (populated by DB trigger, not by application code)
    search_vector = Column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index("ix_resources_resource_type", "resource_type"),
        Index("ix_resources_status", "status"),
        Index("ix_resources_owner", "owner"),
        Index("ix_resources_format_tags", "format_tags", postgresql_using="gin"),
        Index("ix_resources_organisms", "organisms", postgresql_using="gin"),
        Index("ix_resources_modeling_scales", "modeling_scales", postgresql_using="gin"),
        Index("ix_resources_domains", "domains", postgresql_using="gin"),
    )


class RunModel(Base):
    """SQLAlchemy model for the ``runs`` table."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("resources.id"))
    model_version: Mapped[str] = mapped_column(String(100), default="")
    input_resource_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    output_resource_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    parameters: Mapped[Any] = mapped_column(JSONB, default=dict)
    environment: Mapped[Any] = mapped_column(JSONB, nullable=True)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, values_callable=_enum_values, name="runstatus", create_type=False),
        default=RunStatus.REGISTERED,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str] = mapped_column(Text, default="")
    log_uri: Mapped[str] = mapped_column(Text, default="")
    triggered_by: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_runs_model_id", "model_id"),
        Index("ix_runs_status", "status"),
        Index("ix_runs_triggered_by", "triggered_by"),
        Index("ix_runs_input_resource_ids", "input_resource_ids", postgresql_using="gin"),
        Index("ix_runs_output_resource_ids", "output_resource_ids", postgresql_using="gin"),
    )


# ── Filter / aggregation field maps ──────────────────────────────────

_FILTER_COLUMN_MAP: dict[str, Any] = {
    "resource_type": ResourceModel.resource_type,
    "status": ResourceModel.status,
    "execution_type": ResourceModel.execution_type,
    "owner": ResourceModel.owner,
    "organisms": ResourceModel.organisms,
    "domains": ResourceModel.domains,
    "modeling_scales": ResourceModel.modeling_scales,
    "format_tags": ResourceModel.format_tags,
    "created_at": ResourceModel.created_at,
    "updated_at": ResourceModel.updated_at,
    "date_published": ResourceModel.date_published,
}

_ARRAY_FIELDS: frozenset[str] = frozenset(
    {
        "organisms",
        "domains",
        "modeling_scales",
        "format_tags",
    }
)


# ── Serialization Helpers ────────────────────────────────────────────


def _serialize_io_spec(spec: IOSpec | None) -> dict[str, Any] | None:
    if spec is None:
        return None
    return dataclasses.asdict(spec)


def _deserialize_io_spec(data: Any) -> IOSpec | None:
    if data is None:
        return None
    inputs = tuple(IOSlot(**s) for s in data.get("inputs", []))
    outputs = tuple(IOSlot(**s) for s in data.get("outputs", []))
    return IOSpec(
        inputs=inputs,
        outputs=outputs,
        parameters_schema=data.get("parameters_schema"),
    )


def _serialize_authors(authors: list[Author]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(a) for a in authors]


def _deserialize_authors(data: Any) -> list[Author]:
    if not data:
        return []
    return [Author(**a) for a in data]


def _serialize_publications(pubs: list[Publication]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(p) for p in pubs]


def _deserialize_publications(data: Any) -> list[Publication]:
    if not data:
        return []
    return [Publication(**p) for p in data]


def _serialize_environment(env: RunEnvironment | None) -> dict[str, Any] | None:
    if env is None:
        return None
    return dataclasses.asdict(env)


def _deserialize_environment(data: Any) -> RunEnvironment | None:
    if not data:
        return None
    return RunEnvironment(**data)


# ── Domain ↔ Database Mapping ────────────────────────────────────────


def resource_to_db(resource: Resource) -> ResourceModel:
    """Convert a domain Resource to a SQLAlchemy ResourceModel."""
    return ResourceModel(
        id=resource.id,
        name=resource.name,
        resource_type=resource.resource_type,
        location_uri=resource.location_uri,
        description=resource.description,
        version=resource.version,
        status=resource.status,
        new_version_of=resource.new_version_of or None,
        superseded_by=resource.superseded_by or None,
        authors=_serialize_authors(resource.authors),
        organization=resource.organization,
        contact_email=resource.contact_email,
        publications=_serialize_publications(resource.publications),
        funding=resource.funding,
        modeling_scales=resource.modeling_scales,
        organisms=resource.organisms,
        domains=resource.domains,
        date_published=resource.date_published,
        format_tags=resource.format_tags,
        digest_sha256=resource.digest_sha256,
        size_bytes=resource.size_bytes,
        external_ids=resource.external_ids,
        license=resource.license,
        execution_type=resource.execution_type,
        execution_ref=resource.execution_ref,
        io_spec=_serialize_io_spec(resource.io_spec),
        owner=resource.owner,
        metadata_=resource.metadata,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


def resource_from_db(model: ResourceModel) -> Resource:
    """Convert a SQLAlchemy ResourceModel to a domain Resource."""
    return Resource(
        id=model.id,
        name=model.name,
        resource_type=model.resource_type,
        location_uri=model.location_uri,
        description=model.description,
        version=model.version,
        status=model.status,
        new_version_of=model.new_version_of or "",
        superseded_by=model.superseded_by or "",
        authors=_deserialize_authors(model.authors),
        organization=model.organization,
        contact_email=model.contact_email,
        publications=_deserialize_publications(model.publications),
        funding=model.funding or [],
        modeling_scales=model.modeling_scales or [],
        organisms=model.organisms or [],
        domains=model.domains or [],
        date_published=model.date_published,
        format_tags=model.format_tags or [],
        digest_sha256=model.digest_sha256,
        size_bytes=model.size_bytes,
        external_ids=model.external_ids or {},
        license=model.license,
        execution_type=model.execution_type,
        execution_ref=model.execution_ref,
        io_spec=_deserialize_io_spec(model.io_spec),
        owner=model.owner,
        metadata=model.metadata_ or {},
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def run_to_db(run: Run) -> RunModel:
    """Convert a domain Run to a SQLAlchemy RunModel."""
    return RunModel(
        id=run.id,
        model_id=run.model_id,
        model_version=run.model_version,
        input_resource_ids=run.input_resource_ids,
        output_resource_ids=run.output_resource_ids,
        parameters=run.parameters,
        environment=_serialize_environment(run.environment),
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        log_uri=run.log_uri,
        triggered_by=run.triggered_by,
        notes=run.notes,
        created_at=run.created_at,
    )


def run_from_db(model: RunModel) -> Run:
    """Convert a SQLAlchemy RunModel to a domain Run."""
    return Run(
        id=model.id,
        model_id=model.model_id,
        model_version=model.model_version,
        input_resource_ids=model.input_resource_ids or [],
        output_resource_ids=model.output_resource_ids or [],
        parameters=model.parameters or {},
        environment=_deserialize_environment(model.environment),
        status=model.status,
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_message=model.error_message or "",
        log_uri=model.log_uri or "",
        triggered_by=model.triggered_by or "",
        notes=model.notes or "",
        created_at=model.created_at,
    )


# ── PostgresRegistry ─────────────────────────────────────────────────

_MAX_VERSION_DEPTH = 100


class PostgresRegistry:
    """Postgres-backed Registry implementation.

    Requires a SQLAlchemy ``Session``. The caller manages session lifecycle
    (creation, commit, rollback, close). This keeps the registry testable
    and allows the API layer to control transaction boundaries.

    The registry calls ``flush()`` but never ``commit()`` — the caller
    decides when to commit.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Resource CRUD ────────────────────────────────────────────────

    def register_resource(self, resource: Resource) -> Resource:
        existing = self._session.get(ResourceModel, resource.id)
        if existing is not None:
            raise DuplicateResourceError(resource.id)
        model = resource_to_db(resource)
        self._session.add(model)
        self._session.flush()
        return resource_from_db(model)

    def get_resource(self, resource_id: str) -> Resource:
        model = self._session.get(ResourceModel, resource_id)
        if model is None:
            raise ResourceNotFoundError(resource_id)
        return resource_from_db(model)

    def find_resources(
        self,
        *,
        resource_type: ResourceType | None = None,
        tags: list[str] | None = None,
        owner: str | None = None,
        name_contains: str | None = None,
        organisms: list[str] | None = None,
        scales: list[str] | None = None,
        domains: list[str] | None = None,
        status: ResourceStatus | None = None,
        date_published_after: date | None = None,
        date_published_before: date | None = None,
    ) -> list[Resource]:
        stmt = select(ResourceModel)
        if resource_type is not None:
            stmt = stmt.where(ResourceModel.resource_type == resource_type)
        if tags is not None:
            # Resource must contain ALL requested tags (@> operator)
            stmt = stmt.where(ResourceModel.format_tags.contains(tags))
        if owner is not None:
            stmt = stmt.where(ResourceModel.owner == owner)
        if name_contains is not None:
            stmt = stmt.where(ResourceModel.name.ilike(f"%{name_contains}%"))
        if organisms is not None:
            # Resource must share at least one organism (&& operator)
            stmt = stmt.where(ResourceModel.organisms.overlap(organisms))
        if scales is not None:
            stmt = stmt.where(ResourceModel.modeling_scales.overlap(scales))
        if domains is not None:
            stmt = stmt.where(ResourceModel.domains.overlap(domains))
        if status is not None:
            stmt = stmt.where(ResourceModel.status == status)
        if date_published_after is not None:
            stmt = stmt.where(ResourceModel.date_published >= date_published_after)
        if date_published_before is not None:
            stmt = stmt.where(ResourceModel.date_published <= date_published_before)
        results = self._session.execute(stmt).scalars().all()
        return [resource_from_db(m) for m in results]

    # ── Full-text search with filters & aggregations ──────────────────

    def search_resources(self, query: SearchQuery) -> SearchResult:
        """Execute a full-text search with structured filters and aggregations.

        This method is Postgres-specific (tsvector, unnest) and is NOT part
        of the generic Registry protocol.
        """
        from mism_registry.search import AGGREGATABLE_FIELDS, AggBucket

        # -- Build shared WHERE conditions --------------------------------
        conditions = self._build_filter_conditions(query.filters)

        ts_query = None
        if query.text:
            ts_query = func.plainto_tsquery("english", query.text)
            conditions.append(ResourceModel.search_vector.op("@@")(ts_query))

        # -- Main query: paginated results --------------------------------
        stmt = select(ResourceModel)
        if ts_query is not None:
            rank = func.ts_rank_cd(ResourceModel.search_vector, ts_query)
            stmt = stmt.add_columns(rank.label("score"))

        for cond in conditions:
            stmt = stmt.where(cond)

        # Sorting
        if query.sort_field == "_score" and ts_query is not None:
            stmt = stmt.order_by(literal_column("score").desc())
        elif query.sort_field == "_score":
            # No text query — fall back to created_at
            stmt = stmt.order_by(ResourceModel.created_at.desc())
        else:
            col = getattr(ResourceModel, query.sort_field, ResourceModel.created_at)
            if query.sort_order == "asc":
                stmt = stmt.order_by(col.asc())
            else:
                stmt = stmt.order_by(col.desc())

        stmt = stmt.limit(query.limit).offset(query.offset)
        rows = self._session.execute(stmt).all()

        if ts_query is not None:
            resources = [resource_from_db(row[0]) for row in rows]
            scores: list[float] | None = [float(row[1]) for row in rows]
        else:
            resources = [resource_from_db(row[0]) for row in rows]
            scores = None

        # -- Total count --------------------------------------------------
        count_stmt = select(func.count()).select_from(ResourceModel)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        total: int = self._session.execute(count_stmt).scalar_one()

        # -- Aggregations -------------------------------------------------
        aggs: dict[str, list[AggBucket]] = {}
        for field_name in query.agg_fields:
            if field_name not in AGGREGATABLE_FIELDS:
                continue
            aggs[field_name] = self._run_aggregation(field_name, conditions)

        return SearchResult(
            total=total,
            resources=resources,
            scores=scores,
            aggs=aggs,
        )

    def _build_filter_conditions(self, filters: tuple) -> list:
        """Convert FieldFilter tuples into SQLAlchemy WHERE conditions."""

        conditions: list = []
        for f in filters:
            col = _FILTER_COLUMN_MAP.get(f.field)
            if col is None:
                continue

            if f.op == "eq":
                conditions.append(col == f.value)
            elif f.op == "overlap":
                val = f.value if isinstance(f.value, list) else [f.value]
                conditions.append(col.overlap(val))
            elif f.op == "contains":
                val = f.value if isinstance(f.value, list) else [f.value]
                conditions.append(col.contains(val))
            elif f.op == "gte":
                if isinstance(f.value, str):
                    conditions.append(col >= f.value)
                else:
                    conditions.append(col >= f.value)
            elif f.op == "lte":
                if isinstance(f.value, str):
                    conditions.append(col <= f.value)
                else:
                    conditions.append(col <= f.value)
        return conditions

    def _run_aggregation(self, field_name: str, conditions: list) -> list:
        """Run a single aggregation query for a field."""
        from mism_registry.search import AggBucket

        col = _FILTER_COLUMN_MAP.get(field_name)
        if col is None:
            return []

        # Array fields need unnest; scalar fields use GROUP BY directly
        if field_name in _ARRAY_FIELDS:
            val = func.unnest(col).label("val")
            agg_stmt = select(val, func.count().label("cnt")).select_from(ResourceModel)
            for cond in conditions:
                agg_stmt = agg_stmt.where(cond)
            agg_stmt = agg_stmt.group_by(literal_column("val")).order_by(
                literal_column("cnt").desc()
            )
        else:
            agg_stmt = select(col.label("val"), func.count().label("cnt")).select_from(
                ResourceModel
            )
            for cond in conditions:
                agg_stmt = agg_stmt.where(cond)
            agg_stmt = agg_stmt.group_by(col).order_by(literal_column("cnt").desc())

        rows = self._session.execute(agg_stmt).all()
        buckets = []
        for row in rows:
            if row.val is None:
                continue
            # Enum columns return Python enum instances — use .value for the string
            val = row.val
            key = val.value if hasattr(val, "value") else str(val)
            buckets.append(AggBucket(key=key, count=row.cnt))
        return buckets

    def update_resource(self, resource: Resource) -> Resource:
        model = self._session.get(ResourceModel, resource.id)
        if model is None:
            raise ResourceNotFoundError(resource.id)
        model.name = resource.name
        model.resource_type = resource.resource_type
        model.location_uri = resource.location_uri
        model.description = resource.description
        model.version = resource.version
        model.status = resource.status
        model.new_version_of = resource.new_version_of or None
        model.superseded_by = resource.superseded_by or None
        model.authors = _serialize_authors(resource.authors)
        model.organization = resource.organization
        model.contact_email = resource.contact_email
        model.publications = _serialize_publications(resource.publications)
        model.funding = resource.funding
        model.modeling_scales = resource.modeling_scales
        model.organisms = resource.organisms
        model.domains = resource.domains
        model.date_published = resource.date_published
        model.format_tags = resource.format_tags
        model.digest_sha256 = resource.digest_sha256
        model.size_bytes = resource.size_bytes
        model.external_ids = resource.external_ids
        model.license = resource.license
        model.execution_type = resource.execution_type
        model.execution_ref = resource.execution_ref
        model.io_spec = _serialize_io_spec(resource.io_spec)
        model.owner = resource.owner
        model.metadata_ = resource.metadata
        model.updated_at = resource.updated_at
        self._session.flush()
        return resource_from_db(model)

    # ── Run CRUD ─────────────────────────────────────────────────────

    def create_run(self, run: Run) -> Run:
        model = run_to_db(run)
        self._session.add(model)
        self._session.flush()
        return run_from_db(model)

    def get_run(self, run_id: str) -> Run:
        model = self._session.get(RunModel, run_id)
        if model is None:
            raise RunNotFoundError(run_id)
        return run_from_db(model)

    def update_run(self, run: Run) -> Run:
        model = self._session.get(RunModel, run.id)
        if model is None:
            raise RunNotFoundError(run.id)
        model.model_id = run.model_id
        model.model_version = run.model_version
        model.input_resource_ids = run.input_resource_ids
        model.output_resource_ids = run.output_resource_ids
        model.parameters = run.parameters
        model.environment = _serialize_environment(run.environment)
        model.status = run.status
        model.started_at = run.started_at
        model.completed_at = run.completed_at
        model.error_message = run.error_message
        model.log_uri = run.log_uri
        model.triggered_by = run.triggered_by
        model.notes = run.notes
        self._session.flush()
        return run_from_db(model)

    def find_runs(
        self,
        *,
        model_id: str | None = None,
        input_resource_id: str | None = None,
        status: RunStatus | None = None,
    ) -> list[Run]:
        stmt = select(RunModel)
        if model_id is not None:
            stmt = stmt.where(RunModel.model_id == model_id)
        if input_resource_id is not None:
            stmt = stmt.where(RunModel.input_resource_ids.contains([input_resource_id]))
        if status is not None:
            stmt = stmt.where(RunModel.status == status)
        results = self._session.execute(stmt).scalars().all()
        return [run_from_db(m) for m in results]

    # ── Lineage ──────────────────────────────────────────────────────

    def get_lineage(self, resource_id: str) -> list[Run]:
        stmt = select(RunModel).where(RunModel.output_resource_ids.contains([resource_id]))
        results = self._session.execute(stmt).scalars().all()
        return [run_from_db(m) for m in results]

    def get_dependents(self, resource_id: str) -> list[Run]:
        stmt = select(RunModel).where(RunModel.input_resource_ids.contains([resource_id]))
        results = self._session.execute(stmt).scalars().all()
        return [run_from_db(m) for m in results]

    def get_model_run_details(
        self,
        model_id: str,
        *,
        status: RunStatus | None = None,
    ) -> ModelRunSummary:
        """Fetch all runs for a model with hydrated input/output Resources.

        Optimized for Postgres: fetches the model in one query, all runs
        in a second, and all referenced resources in a single batch
        ``WHERE id IN (...)`` query instead of N+1 calls.
        """
        # 1. Fetch the model resource
        model_row = self._session.get(ResourceModel, model_id)
        if model_row is None:
            raise ResourceNotFoundError(model_id)
        model = resource_from_db(model_row)

        # 2. Fetch all runs for this model
        run_stmt = select(RunModel).where(RunModel.model_id == model_id)
        if status is not None:
            run_stmt = run_stmt.where(RunModel.status == status)
        run_rows = self._session.execute(run_stmt).scalars().all()
        runs = [run_from_db(r) for r in run_rows]

        # 3. Collect all unique resource IDs referenced by runs
        all_resource_ids: set[str] = set()
        for run in runs:
            all_resource_ids.update(run.input_resource_ids)
            all_resource_ids.update(run.output_resource_ids)

        # 4. Batch-fetch all resources in one query
        resource_cache: dict[str, Resource] = {}
        if all_resource_ids:
            res_stmt = select(ResourceModel).where(ResourceModel.id.in_(all_resource_ids))
            res_rows = self._session.execute(res_stmt).scalars().all()
            for row in res_rows:
                resource_cache[row.id] = resource_from_db(row)

        # 5. Assemble enriched run details
        details = [
            ModelRunDetail(
                run=run,
                input_resources=[resource_cache[rid] for rid in run.input_resource_ids],
                output_resources=[resource_cache[rid] for rid in run.output_resource_ids],
            )
            for run in runs
        ]
        return ModelRunSummary(model=model, runs=details)

    # ── Versioning ───────────────────────────────────────────────────

    def get_latest_version(self, resource_id: str) -> Resource | None:
        model = self._session.get(ResourceModel, resource_id)
        if model is None:
            return None
        current = model
        for _ in range(_MAX_VERSION_DEPTH):
            if not current.superseded_by:
                break
            next_model = self._session.get(ResourceModel, current.superseded_by)
            if next_model is None:
                break
            current = next_model
        return resource_from_db(current)

    def get_version_history(self, resource_id: str) -> list[Resource]:
        model = self._session.get(ResourceModel, resource_id)
        if model is None:
            return []
        # Walk backward to the oldest version
        current = model
        for _ in range(_MAX_VERSION_DEPTH):
            if not current.new_version_of:
                break
            prev_model = self._session.get(ResourceModel, current.new_version_of)
            if prev_model is None:
                break
            current = prev_model
        # Walk forward, collecting the full chain oldest-first
        chain: list[Resource] = [resource_from_db(current)]
        for _ in range(_MAX_VERSION_DEPTH):
            if not current.superseded_by:
                break
            next_model = self._session.get(ResourceModel, current.superseded_by)
            if next_model is None:
                break
            current = next_model
            chain.append(resource_from_db(current))
        return chain


# ── Session Factory Helpers ──────────────────────────────────────────


def create_session_factory(
    database_url: str,
    *,
    pool_pre_ping: bool = True,
    pool_recycle: int = 1800,
) -> sessionmaker[Session]:
    """Create a SQLAlchemy session factory bound to the given database URL."""
    engine = create_engine(database_url, pool_pre_ping=pool_pre_ping, pool_recycle=pool_recycle)
    return sessionmaker(bind=engine)


def create_registry(database_url: str) -> tuple[PostgresRegistry, Session]:
    """Convenience for simple scripts.

    Returns a ``(registry, session)`` tuple. The caller must call
    ``session.commit()`` to persist changes and ``session.close()``
    when done. For production use, manage sessions through your API
    layer's dependency injection.
    """
    factory = create_session_factory(database_url)
    session = factory()
    return PostgresRegistry(session), session
