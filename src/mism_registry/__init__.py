"""MISM Registry: FAIR-ready metadata registry for the MISM ecosystem."""

from ._version import __version__
from .enums import ExecutionType, ResourceType, RunStatus
from .errors import (
    DuplicateResourceError,
    InvalidStateTransitionError,
    IOSpecMismatchError,
    MismRegistryError,
    ResourceNotFoundError,
    RunNotFoundError,
    ValidationError,
)
from .in_memory import InMemoryRegistry
from .operations import (
    cancel_run,
    complete_run,
    fail_run,
    find_resources,
    find_runs,
    get_dependents,
    get_lineage,
    prepare_run,
    register_dataset,
    register_model,
    start_run,
)
from .protocol import Registry
from .resource import Resource
from .run import Run
from .types import IOSlot, IOSpec, RunEnvironment

__all__ = [
    "__version__",
    # Enums
    "ResourceType",
    "ExecutionType",
    "RunStatus",
    # Data model
    "IOSlot",
    "IOSpec",
    "RunEnvironment",
    "Resource",
    "Run",
    # Errors
    "MismRegistryError",
    "ResourceNotFoundError",
    "RunNotFoundError",
    "ValidationError",
    "DuplicateResourceError",
    "IOSpecMismatchError",
    "InvalidStateTransitionError",
    # Protocol & Implementation
    "Registry",
    "InMemoryRegistry",
    # Operations
    "register_dataset",
    "register_model",
    "prepare_run",
    "start_run",
    "complete_run",
    "fail_run",
    "cancel_run",
    "find_resources",
    "find_runs",
    "get_lineage",
    "get_dependents",
]
