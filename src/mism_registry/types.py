"""Value objects: Author, Publication, IOSlot, IOSpec, RunEnvironment."""

from __future__ import annotations

import dataclasses
import re
import shlex
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
    pmid: str = ""  # PubMed ID (schema.md Section A publications)
    url: str = ""
    citation: str = ""

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Publication.title must be non-empty")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Contact:
    """How to reach someone about the model now (schema.md model.contacts)."""

    name: str
    role: str = ""  # "corresponding author" | "maintainer" | "support" | "submitter"
    email: str = ""
    affiliation: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Contact.name must be non-empty")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class RelatedResource:
    """A linked data source or prior model (schema.md model.related_resources)."""

    qualifier: str  # e.g. "bqmodel:isDerivedFrom", "bqbiol:isVersionOf"
    scheme: str = ""  # identifier scheme
    value: str = ""  # identifier value


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


# ── Execution characterization (schema.md Section B, values only) ────────


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Dependency:
    """A single runtime/optional/system dependency."""

    name: str
    version_constraint: str = ""
    kind: str = "runtime"  # "runtime" | "optional" | "system"
    group: str = ""  # optional-dependency group name

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Dependency.name must be non-empty")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Container:
    """A container recipe (schema.md execution.containers)."""

    kind: str  # "docker" | "singularity"
    file: str = ""  # "Dockerfile" | "container.def"
    image_name: str = ""
    registry: str = ""  # e.g. "ghcr.io/mism-center" — captured at image-check approval


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Compute:
    """Compute requirements (schema.md execution.compute), values only."""

    cpu_cores: int | None = None
    memory_gb: float | None = None
    gpu_required: bool | None = None
    parallelism: str = ""  # "single" | "multi-thread" | "MPI" | "GPU" | ...
    typical_runtime: float | None = None
    typical_runtime_unit: str = ""  # e.g. "minutes", "hours"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Argument:
    """A documented argument to an entry-point command."""

    name: str
    description: str = ""
    default: Any = None
    enums: tuple[str, ...] | None = None  # allowed values, if constrained
    data_type: str | None = ""  # e.g. "int", "str", "path"
    position: int | None = 0  # positional index; 0 = unassigned
    user_can_override: bool | None = None  # may caller change this at run time

    def __post_init__(self) -> None:
        # position 0 means "unassigned" (see EntryPoint uniqueness check).
        if self.position is not None and self.position < 0:
            raise ValueError("Argument.position must be >= 0")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class EntryPoint:
    """One invocable command (schema.md execution.entry_points)."""

    command: str
    purpose: str = ""
    arguments: tuple[Argument, ...] = ()

    def __post_init__(self) -> None:
        if not self.command.strip():
            raise ValueError("EntryPoint.command must be non-empty")
        # Enforce unique positions, ignoring the 0/None "unassigned" sentinel.
        assigned = [a.position for a in self.arguments if a.position]
        if len(assigned) != len(set(assigned)):
            raise ValueError("EntryPoint argument positions must be unique")

    def to_cli(self, values: dict[str, Any] | None = None) -> str:
        """Render a runnable command string from arg values (falls back to
        each argument's default). Requires canonical arg names: a flag token
        like "--topology" or a bare positional name like "experiment_id" —
        NOT doc labels like "--topology / -t"."""
        values = values or {}
        # Drop <placeholder> tokens from the base command; positionals fill them.
        base = re.sub(r"\s*<[^>]*>", "", self.command).strip()
        parts = [base]
        # Positionals first, in position order; then options.
        positional = sorted(
            (a for a in self.arguments if a.position),
            key=lambda a: a.position or 0,
        )
        options = [a for a in self.arguments if not a.position]
        for arg in positional:
            val = values.get(arg.name, arg.default)
            if val is not None:
                parts.append(shlex.quote(str(val)))
        for arg in options:
            val = values.get(arg.name, arg.default)
            if arg.data_type == "bool":
                if val:  # presence flag: emit token only when truthy
                    parts.append(arg.name)
            elif val is not None:  # valued option: token + value
                parts.extend([arg.name, shlex.quote(str(val))])
        return " ".join(parts)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class TestSpec:
    """Test framework + invocation (schema.md execution.tests)."""

    framework: str = ""  # "pytest" | "unittest" | ...
    invocation: str = ""


# ── I/O characterization (schema.md Section C, values only) ──────────────
# ponytail: separate from IOSpec/IOSlot above (which drive the run handshake).
# Consolidate the two io representations later if a use case needs it.


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Parameter:
    """A scalar/array configuration value (io.inputs.parameters)."""

    name: str
    description: str = ""
    default_value: Any = None
    unit: str = ""  # UO label, ontology IRI dropped for now
    biological_meaning: str = ""


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class InitialCondition:
    """An initial population/field/state value (io.inputs.initial_conditions)."""

    name: str
    value: Any = None
    unit: str = ""


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class DataInput:
    """An external input file (io.inputs.data_inputs)."""

    name: str
    purpose: str = ""
    format: str = ""  # EDAM format label, IRI dropped for now
    required: bool = True


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Output:
    """A produced output (io.outputs)."""

    name: str
    description: str = ""
    quantity_kind: str = ""
    unit: str = ""
    format: str = ""
    destination: str = ""


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentProtocol:
    """MIASE-style run setup (io.experiment_protocol), values only."""

    description: str = ""
    timestep: float | None = None
    timestep_unit: str = ""
    duration: float | None = None
    duration_unit: str = ""
    observables: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class IODetail:
    """Rich I/O characterization from schema.md Section C."""

    parameters: tuple[Parameter, ...] = ()
    initial_conditions: tuple[InitialCondition, ...] = ()
    data_inputs: tuple[DataInput, ...] = ()
    outputs: tuple[Output, ...] = ()
    experiment_protocol: ExperimentProtocol | None = None
