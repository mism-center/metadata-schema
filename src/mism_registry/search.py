"""Domain types for full-text search with filters and aggregations."""

from __future__ import annotations

import dataclasses
from typing import Any

from .resource import Resource


@dataclasses.dataclass(frozen=True, slots=True)
class FieldFilter:
    """A single filter clause: field + operator + value."""

    field: str
    op: str  # "eq", "overlap", "contains", "gte", "lte"
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
    "resource_type": ("scalar", frozenset({"eq"})),
    "status": ("scalar", frozenset({"eq"})),
    "execution_type": ("scalar", frozenset({"eq"})),
    "owner": ("scalar", frozenset({"eq"})),
    "organisms": ("array", frozenset({"overlap", "contains"})),
    "domains": ("array", frozenset({"overlap", "contains"})),
    "modeling_scales": ("array", frozenset({"overlap", "contains"})),
    "format_tags": ("array", frozenset({"overlap", "contains"})),
    "created_at": ("datetime", frozenset({"gte", "lte"})),
    "updated_at": ("datetime", frozenset({"gte", "lte"})),
    "date_published": ("date", frozenset({"gte", "lte"})),
}

AGGREGATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "resource_type",
        "status",
        "execution_type",
        "owner",
        "organisms",
        "domains",
        "modeling_scales",
        "format_tags",
    }
)
