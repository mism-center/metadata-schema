"""Domain types for full-text search with filters and aggregations."""

from __future__ import annotations

import dataclasses
from typing import Any

from .resource import Resource


@dataclasses.dataclass(frozen=True, slots=True)
class FieldFilter:
    """A single filter clause: field + operator + value."""

    field: str
    op: str  # "eq", "in", "overlap", "contains", "gte", "lte"
    value: Any  # str, list[str], datetime string, etc.


@dataclasses.dataclass(frozen=True, slots=True)
class SearchQuery:
    """Storage-agnostic search request."""

    text: str | None = None
    filters: tuple[FieldFilter, ...] = ()
    agg_fields: tuple[str, ...] = ()
    sort_field: str = "created_at"
    sort_order: str = "desc"
    limit: int = 25
    offset: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class AggBucket:
    """A single aggregation bucket."""

    key: str
    count: int


@dataclasses.dataclass(frozen=True, slots=True)
class SearchResult:
    """Result of a search query with optional scores and aggregations."""

    total: int
    resources: list[Resource]
    scores: list[float] | None = None
    aggs: dict[str, list[AggBucket]] = dataclasses.field(default_factory=dict)


# ── Field metadata for validation ────────────────────────────────────

# Maps field name → (column_kind, allowed_ops)
# column_kind: "scalar" | "array" | "datetime"
FILTERABLE_FIELDS: dict[str, tuple[str, frozenset[str]]] = {
    "resource_type": ("scalar", frozenset({"eq", "in"})),
    "version_status": ("scalar", frozenset({"eq", "in"})),
    "registration_status": ("scalar", frozenset({"eq", "in"})),
    "image_review_status": ("scalar", frozenset({"eq", "in"})),
    "execution_type": ("scalar", frozenset({"eq", "in"})),
    "owner": ("scalar", frozenset({"eq", "in"})),
    "organization": ("scalar", frozenset({"eq", "in"})),
    "license": ("scalar", frozenset({"eq", "in"})),
    # Characterization vocabularies (schema.md Section A). `multiscale` is a
    # nullable bool, so `in` would be meaningless — `eq` only.
    "determinism": ("scalar", frozenset({"eq", "in"})),
    "time_dynamics": ("scalar", frozenset({"eq", "in"})),
    "spatial": ("scalar", frozenset({"eq", "in"})),
    "multiscale": ("scalar", frozenset({"eq"})),
    "organisms": ("array", frozenset({"overlap", "contains"})),
    "domains": ("array", frozenset({"overlap", "contains"})),
    "model_scales": ("array", frozenset({"overlap", "contains"})),
    "format_tags": ("array", frozenset({"overlap", "contains"})),
    "model_class": ("array", frozenset({"overlap", "contains"})),
    "formalism": ("array", frozenset({"overlap", "contains"})),
    # Biology (schema.md Section D).
    "infectious_agents": ("array", frozenset({"overlap", "contains"})),
    "health_conditions": ("array", frozenset({"overlap", "contains"})),
    "biological_processes": ("array", frozenset({"overlap", "contains"})),
    "molecular_entities": ("array", frozenset({"overlap", "contains"})),
    "proteins_genes": ("array", frozenset({"overlap", "contains"})),
    "created_at": ("datetime", frozenset({"gte", "lte"})),
    "updated_at": ("datetime", frozenset({"gte", "lte"})),
    "date_published": ("date", frozenset({"gte", "lte"})),
}

# Every filterable field except the date/datetime ones, which have no term
# buckets to count.
AGGREGATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "resource_type",
        "version_status",
        "registration_status",
        "image_review_status",
        "execution_type",
        "owner",
        "organization",
        "license",
        "determinism",
        "time_dynamics",
        "spatial",
        "multiscale",
        "organisms",
        "domains",
        "model_scales",
        "format_tags",
        "model_class",
        "formalism",
        "infectious_agents",
        "health_conditions",
        "biological_processes",
        "molecular_entities",
        "proteins_genes",
    }
)
