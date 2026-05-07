"""Registry protocol — storage-agnostic interface."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from .enums import ResourceStatus, ResourceType, RunStatus
from .resource import Resource
from .run import Run
from .run_detail import ModelRunSummary


@runtime_checkable
class Registry(Protocol):
    """Storage-agnostic interface for the MISM registry.

    Any backend (in-memory, PostgreSQL) can implement this protocol.
    """

    def register_resource(self, resource: Resource) -> Resource: ...

    def get_resource(self, resource_id: str) -> Resource: ...

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
    ) -> list[Resource]: ...

    def update_resource(self, resource: Resource) -> Resource: ...

    def create_run(self, run: Run) -> Run: ...

    def get_run(self, run_id: str) -> Run: ...

    def update_run(self, run: Run) -> Run: ...

    def find_runs(
        self,
        *,
        model_id: str | None = None,
        input_resource_id: str | None = None,
        status: RunStatus | None = None,
    ) -> list[Run]: ...

    def get_lineage(self, resource_id: str) -> list[Run]: ...

    def get_dependents(self, resource_id: str) -> list[Run]: ...

    def get_model_run_details(
        self,
        model_id: str,
        *,
        status: RunStatus | None = None,
    ) -> ModelRunSummary: ...

    def get_latest_version(self, resource_id: str) -> Resource | None: ...

    def get_version_history(self, resource_id: str) -> list[Resource]: ...
