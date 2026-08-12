"""Consistency of the search field registries.

Whether a field can be filtered is declared in four places that have to agree,
and nothing at runtime complains when they don't:

    search.FILTERABLE_FIELDS          field -> (column kind, allowed ops)
    search.AGGREGATABLE_FIELDS        which fields can produce term buckets
    postgres._FILTER_COLUMN_MAP       field -> SQLAlchemy column
    postgres._ARRAY_FIELDS            which need unnest / overlap

The failure mode is silent, which is why these are worth asserting: a field
declared filterable but missing from ``_FILTER_COLUMN_MAP`` is skipped by
``_build_filter_conditions``, so the filter is dropped and the caller gets
*unfiltered* results that look successful.

Pure unit tests — no database. The Postgres integration fixture drops every
table, so a guard this cheap should not depend on it.
"""

from __future__ import annotations

from mism_registry.backends.postgres import (
    _ARRAY_FIELDS,
    _FILTER_COLUMN_MAP,
    ResourceModel,
)
from mism_registry.search import AGGREGATABLE_FIELDS, FILTERABLE_FIELDS

_TEMPORAL_KINDS = frozenset({"datetime", "date"})


def test_every_filterable_field_maps_to_a_column() -> None:
    missing = sorted(set(FILTERABLE_FIELDS) - set(_FILTER_COLUMN_MAP))
    assert not missing, (
        f"declared filterable but absent from _FILTER_COLUMN_MAP, so filters on "
        f"them are silently dropped: {missing}"
    )


def test_no_columns_mapped_without_being_declared_filterable() -> None:
    orphans = sorted(set(_FILTER_COLUMN_MAP) - set(FILTERABLE_FIELDS))
    assert not orphans, (
        f"mapped to a column but not declared in FILTERABLE_FIELDS, so ops are "
        f"unvalidated and the field defaults to 'scalar' coercion: {orphans}"
    )


def test_array_fields_match_declared_column_kinds() -> None:
    declared = {field for field, (kind, _) in FILTERABLE_FIELDS.items() if kind == "array"}
    assert declared == _ARRAY_FIELDS, (
        "FILTERABLE_FIELDS and _ARRAY_FIELDS disagree about which columns are "
        f"arrays; only-declared={sorted(declared - _ARRAY_FIELDS)}, "
        f"only-in-_ARRAY_FIELDS={sorted(_ARRAY_FIELDS - declared)}"
    )


def test_aggregatable_fields_are_filterable() -> None:
    # _run_aggregation resolves its column through _FILTER_COLUMN_MAP, so an
    # aggregatable field that isn't filterable returns no buckets at all.
    unknown = sorted(AGGREGATABLE_FIELDS - set(FILTERABLE_FIELDS))
    assert not unknown, f"aggregatable but not filterable: {unknown}"


def test_temporal_fields_are_not_aggregatable() -> None:
    temporal = {field for field, (kind, _) in FILTERABLE_FIELDS.items() if kind in _TEMPORAL_KINDS}
    assert not (AGGREGATABLE_FIELDS & temporal), (
        "term aggregation over a date column would bucket every distinct "
        f"timestamp: {sorted(AGGREGATABLE_FIELDS & temporal)}"
    )


def test_allowed_ops_suit_each_column_kind() -> None:
    set_ops = frozenset({"overlap", "contains"})
    scalar_ops = frozenset({"eq", "in"})
    range_ops = frozenset({"gte", "lte"})

    for field, (kind, ops) in FILTERABLE_FIELDS.items():
        if kind == "array":
            assert ops <= set_ops, f"{field}: array columns take {set_ops}, got {ops}"
        elif kind in _TEMPORAL_KINDS:
            assert ops <= range_ops, f"{field}: got {ops}"
        else:
            assert ops <= scalar_ops, f"{field}: got {ops}"
        assert ops, f"{field}: declared filterable with no allowed operators"


def test_mapped_columns_belong_to_the_resource_model() -> None:
    for field in _FILTER_COLUMN_MAP:
        assert hasattr(ResourceModel, field), (
            f"{field} is mapped for filtering but ResourceModel has no such attribute"
        )
