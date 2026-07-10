"""InMemoryRegistry — dict-backed registry for testing and MVP usage."""

from __future__ import annotations

import copy
from datetime import date

from .enums import ResourceType, ResourceVersionStatus, RunStatus
from .errors import DuplicateResourceError, ResourceNotFoundError, RunNotFoundError
from .resource import Resource
from .run import Run
from .run_detail import ModelRunDetail, ModelRunSummary


class InMemoryRegistry:
    """Dict-backed registry implementation.

    Uses deep copies on store/retrieve to simulate database detachment
    and prevent aliasing bugs.
    """

    def __init__(self) -> None:
        self._resources: dict[str, Resource] = {}
        self._runs: dict[str, Run] = {}

    # ── Resource methods ──────────────────────────────────────────────

    def register_resource(self, resource: Resource) -> Resource:
        if resource.id in self._resources:
            raise DuplicateResourceError(resource.id)
        stored = copy.deepcopy(resource)
        self._resources[stored.id] = stored
        return copy.deepcopy(stored)

    def get_resource(self, resource_id: str) -> Resource:
        if resource_id not in self._resources:
            raise ResourceNotFoundError(resource_id)
        return copy.deepcopy(self._resources[resource_id])

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
        version_status: ResourceVersionStatus | None = None,
        date_published_after: date | None = None,
        date_published_before: date | None = None,
    ) -> list[Resource]:
        results = list(self._resources.values())
        if resource_type is not None:
            results = [r for r in results if r.resource_type == resource_type]
        if tags is not None:
            tag_set = {t.lower() for t in tags}
            results = [r for r in results if tag_set.issubset(set(r.format_tags))]
        if owner is not None:
            results = [r for r in results if r.owner == owner]
        if name_contains is not None:
            needle = name_contains.lower()
            results = [r for r in results if needle in r.name.lower()]
        if organisms is not None:
            org_set = {o.lower() for o in organisms}
            results = [r for r in results if org_set.issubset({o.lower() for o in r.organisms})]
        if scales is not None:
            scale_set = {s.lower() for s in scales}
            results = [
                r for r in results if scale_set.issubset({s.lower() for s in r.model_scales})
            ]
        if domains is not None:
            domain_set = {d.lower() for d in domains}
            results = [r for r in results if domain_set.issubset({d.lower() for d in r.domains})]
        if version_status is not None:
            results = [r for r in results if r.version_status == version_status]
        if date_published_after is not None:
            results = [
                r
                for r in results
                if r.date_published is not None and r.date_published >= date_published_after
            ]
        if date_published_before is not None:
            results = [
                r
                for r in results
                if r.date_published is not None and r.date_published <= date_published_before
            ]
        return [copy.deepcopy(r) for r in results]

    def update_resource(self, resource: Resource) -> Resource:
        if resource.id not in self._resources:
            raise ResourceNotFoundError(resource.id)
        stored = copy.deepcopy(resource)
        self._resources[stored.id] = stored
        return copy.deepcopy(stored)

    # ── Run methods ───────────────────────────────────────────────────

    def create_run(self, run: Run) -> Run:
        stored = copy.deepcopy(run)
        self._runs[stored.id] = stored
        return copy.deepcopy(stored)

    def get_run(self, run_id: str) -> Run:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        return copy.deepcopy(self._runs[run_id])

    def update_run(self, run: Run) -> Run:
        if run.id not in self._runs:
            raise RunNotFoundError(run.id)
        stored = copy.deepcopy(run)
        self._runs[stored.id] = stored
        return copy.deepcopy(stored)

    def find_runs(
        self,
        *,
        model_id: str | None = None,
        input_resource_id: str | None = None,
        status: RunStatus | None = None,
    ) -> list[Run]:
        results = list(self._runs.values())
        if model_id is not None:
            results = [r for r in results if r.model_id == model_id]
        if input_resource_id is not None:
            results = [r for r in results if input_resource_id in r.input_resource_ids]
        if status is not None:
            results = [r for r in results if r.status == status]
        return [copy.deepcopy(r) for r in results]

    # ── Lineage methods ───────────────────────────────────────────────

    def get_lineage(self, resource_id: str) -> list[Run]:
        """Find runs that produced this resource (it appears in output_resource_ids)."""
        return [
            copy.deepcopy(r) for r in self._runs.values() if resource_id in r.output_resource_ids
        ]

    def get_dependents(self, resource_id: str) -> list[Run]:
        """Find runs that consumed this resource (it appears in input_resource_ids)."""
        return [
            copy.deepcopy(r) for r in self._runs.values() if resource_id in r.input_resource_ids
        ]

    def get_model_run_details(
        self,
        model_id: str,
        *,
        status: RunStatus | None = None,
    ) -> ModelRunSummary:
        """Fetch all runs for a model with hydrated input/output Resources."""
        model = self.get_resource(model_id)
        runs = self.find_runs(model_id=model_id, status=status)

        # Collect unique resource IDs and batch-fetch
        all_ids: set[str] = set()
        for run in runs:
            all_ids.update(run.input_resource_ids)
            all_ids.update(run.output_resource_ids)

        cache: dict[str, Resource] = {}
        for rid in all_ids:
            cache[rid] = self.get_resource(rid)

        details = [
            ModelRunDetail(
                run=run,
                input_resources=[cache[rid] for rid in run.input_resource_ids],
                output_resources=[cache[rid] for rid in run.output_resource_ids],
            )
            for run in runs
        ]
        return ModelRunSummary(model=model, runs=details)

    # ── Version methods ───────────────────────────────────────────────

    def get_latest_version(self, resource_id: str) -> Resource | None:
        """Follow the version chain forward to the current active version."""
        if resource_id not in self._resources:
            return None
        current = self._resources[resource_id]
        while current.superseded_by:
            next_id = current.superseded_by
            if next_id not in self._resources:
                break
            current = self._resources[next_id]
        return copy.deepcopy(current)

    def get_version_history(self, resource_id: str) -> list[Resource]:
        """Return the full version chain for a resource, oldest first."""
        if resource_id not in self._resources:
            return []
        # Walk backwards to find the earliest version
        current = self._resources[resource_id]
        while current.new_version_of:
            prev_id = current.new_version_of
            if prev_id not in self._resources:
                break
            current = self._resources[prev_id]
        # Walk forwards collecting all versions
        chain: list[Resource] = [copy.deepcopy(current)]
        while current.superseded_by:
            next_id = current.superseded_by
            if next_id not in self._resources:
                break
            current = self._resources[next_id]
            chain.append(copy.deepcopy(current))
        return chain
