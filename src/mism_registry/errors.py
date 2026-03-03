"""Exception hierarchy for mism-registry."""


class MismRegistryError(Exception):
    """Base exception for all mism-registry errors."""


class ResourceNotFoundError(MismRegistryError):
    """Raised when a resource ID does not exist in the registry."""

    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        super().__init__(f"Resource not found: {resource_id}")


class RunNotFoundError(MismRegistryError):
    """Raised when a run ID does not exist in the registry."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id}")


class ValidationError(MismRegistryError):
    """Raised when entity data fails validation."""


class DuplicateResourceError(MismRegistryError):
    """Raised when attempting to register a resource with a conflicting ID."""

    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        super().__init__(f"Resource already exists: {resource_id}")


class IOSpecMismatchError(MismRegistryError):
    """Raised when input resources don't satisfy model IOSpec tag requirements."""


class InvalidStateTransitionError(MismRegistryError):
    """Raised when a run status transition is illegal."""
