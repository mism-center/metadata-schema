"""MISM Registry: FAIR-ready metadata registry for the MISM ecosystem."""

from ._version import __version__
from .enums import (
    ExecutionType,
    ResourceRegistrationStatus,
    ResourceType,
    ResourceVersionStatus,
    RunStatus,
)
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
    create_new_version,
    fail_run,
    find_resources,
    find_runs,
    get_dependents,
    get_latest_version,
    get_lineage,
    get_model_run_details,
    get_version_history,
    prepare_run,
    register_dataset,
    register_model,
    set_registration_status,
    start_run,
)
from .protocol import Registry
from .resource import Resource
from .run import Run
from .run_detail import ModelRunDetail, ModelRunSummary
from .search import (
    AGGREGATABLE_FIELDS,
    FILTERABLE_FIELDS,
    AggBucket,
    FieldFilter,
    SearchQuery,
    SearchResult,
)
from .types import Author, IOSlot, IOSpec, Publication, RunEnvironment

__all__ = [
    "__version__",
    # Enums
    "ResourceType",
    "ExecutionType",
    "ResourceVersionStatus",
    "ResourceRegistrationStatus",
    "RunStatus",
    # Data model
    "Author",
    "Publication",
    "IOSlot",
    "IOSpec",
    "RunEnvironment",
    "Resource",
    "Run",
    "ModelRunDetail",
    "ModelRunSummary",
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
    # Search
    "SearchQuery",
    "SearchResult",
    "FieldFilter",
    "AggBucket",
    "FILTERABLE_FIELDS",
    "AGGREGATABLE_FIELDS",
    # Operations
    "register_dataset",
    "register_model",
    "create_new_version",
    "set_registration_status",
    "prepare_run",
    "start_run",
    "complete_run",
    "fail_run",
    "cancel_run",
    "find_resources",
    "find_runs",
    "get_lineage",
    "get_dependents",
    "get_latest_version",
    "get_version_history",
    "get_model_run_details",
]
