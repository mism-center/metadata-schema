"""Composite return types for enriched run queries."""

from __future__ import annotations

import dataclasses

from .resource import Resource
from .run import Run


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ModelRunDetail:
    """A single run enriched with hydrated input/output Resources."""

    run: Run
    input_resources: list[Resource]
    output_resources: list[Resource]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ModelRunSummary:
    """All runs for a model, with the model Resource and enriched run details."""

    model: Resource
    runs: list[ModelRunDetail]
