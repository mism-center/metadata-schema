"""Value objects: Author, Publication, IOSlot, IOSpec, RunEnvironment."""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Author:
    """A creator or contributor of a resource."""

    name: str
    orcid: str = ""
    affiliation: str = ""
    role: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Author.name must be non-empty")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Publication:
    """An associated journal paper, preprint, or technical report."""

    title: str
    doi: str = ""
    url: str = ""
    citation: str = ""

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Publication.title must be non-empty")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class IOSlot:
    """A single input or output slot in an IOSpec."""

    name: str
    tags: tuple[str, ...] = ()
    required: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("IOSlot.name must be non-empty")
        normalized = tuple(sorted(set(t.lower().strip() for t in self.tags if t.strip())))
        object.__setattr__(self, "tags", normalized)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class IOSpec:
    """Declares a model's expected inputs and outputs."""

    inputs: tuple[IOSlot, ...] = ()
    outputs: tuple[IOSlot, ...] = ()
    parameters_schema: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        input_names = [s.name for s in self.inputs]
        if len(input_names) != len(set(input_names)):
            raise ValueError("Duplicate input slot names in IOSpec")
        output_names = [s.name for s in self.outputs]
        if len(output_names) != len(set(output_names)):
            raise ValueError("Duplicate output slot names in IOSpec")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class RunEnvironment:
    """Describes where and how execution happened."""

    platform: str = ""
    container_uri: str = ""
    container_digest: str = ""
    conda_env: str = ""
    hardware_description: str = ""
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)
