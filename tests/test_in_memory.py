"""Tests for InMemoryRegistry."""

import pytest

from mism_registry import (
    InMemoryRegistry,
    Resource,
    ResourceType,
    Run,
    RunStatus,
)
from mism_registry.errors import (
    DuplicateResourceError,
    ResourceNotFoundError,
    RunNotFoundError,
)


class TestResourceCRUD:
    def test_register_and_get(self, registry: InMemoryRegistry):
        r = Resource(
            name="data", resource_type=ResourceType.DATASET, location_uri="s3://x"
        )
        registered = registry.register_resource(r)
        assert registered.id == r.id
        retrieved = registry.get_resource(r.id)
        assert retrieved.name == "data"

    def test_get_nonexistent_raises(self, registry: InMemoryRegistry):
        with pytest.raises(ResourceNotFoundError):
            registry.get_resource("nonexistent-id")

    def test_duplicate_registration_raises(self, registry: InMemoryRegistry):
        r = Resource(
            name="data", resource_type=ResourceType.DATASET, location_uri="s3://x"
        )
        registry.register_resource(r)
        with pytest.raises(DuplicateResourceError):
            registry.register_resource(r)

    def test_returned_is_copy(self, registry: InMemoryRegistry):
        r = Resource(
            name="data", resource_type=ResourceType.DATASET, location_uri="s3://x"
        )
        registered = registry.register_resource(r)
        registered.name = "modified"
        retrieved = registry.get_resource(r.id)
        assert retrieved.name == "data"

    def test_update_resource(self, registry: InMemoryRegistry):
        r = Resource(
            name="data", resource_type=ResourceType.DATASET, location_uri="s3://x"
        )
        registry.register_resource(r)
        r.description = "updated"
        registry.update_resource(r)
        retrieved = registry.get_resource(r.id)
        assert retrieved.description == "updated"

    def test_update_nonexistent_raises(self, registry: InMemoryRegistry):
        r = Resource(
            name="data",
            resource_type=ResourceType.DATASET,
            location_uri="s3://x",
            id="no-such-id",
        )
        with pytest.raises(ResourceNotFoundError):
            registry.update_resource(r)


class TestFindResources:
    def _register(self, registry, **kwargs):
        defaults = {
            "name": "test",
            "resource_type": ResourceType.DATASET,
            "location_uri": "s3://x",
        }
        defaults.update(kwargs)
        return registry.register_resource(Resource(**defaults))

    def test_find_by_type(self, registry: InMemoryRegistry):
        self._register(registry, name="d1", resource_type=ResourceType.DATASET)
        self._register(
            registry,
            name="m1",
            resource_type=ResourceType.MODEL,
            location_uri="s3://y",
        )
        results = registry.find_resources(resource_type=ResourceType.DATASET)
        assert len(results) == 1
        assert results[0].name == "d1"

    def test_find_by_tags(self, registry: InMemoryRegistry):
        self._register(registry, name="d1", format_tags=["csv", "timeseries"])
        self._register(
            registry, name="d2", format_tags=["fasta"], location_uri="s3://y"
        )
        results = registry.find_resources(tags=["csv"])
        assert len(results) == 1
        assert results[0].name == "d1"

    def test_find_by_tags_subset(self, registry: InMemoryRegistry):
        self._register(
            registry, name="d1", format_tags=["csv", "timeseries", "extra"]
        )
        results = registry.find_resources(tags=["csv", "timeseries"])
        assert len(results) == 1

    def test_find_by_owner(self, registry: InMemoryRegistry):
        self._register(registry, name="d1", owner="alice")
        self._register(registry, name="d2", owner="bob", location_uri="s3://y")
        results = registry.find_resources(owner="alice")
        assert len(results) == 1
        assert results[0].name == "d1"

    def test_find_by_name_contains(self, registry: InMemoryRegistry):
        self._register(registry, name="SARS-CoV-2 Spike Data")
        self._register(registry, name="Influenza Data", location_uri="s3://y")
        results = registry.find_resources(name_contains="spike")
        assert len(results) == 1
        assert "Spike" in results[0].name

    def test_find_combined_filters(self, registry: InMemoryRegistry):
        self._register(
            registry,
            name="d1",
            resource_type=ResourceType.DATASET,
            format_tags=["csv"],
            owner="alice",
        )
        self._register(
            registry,
            name="d2",
            resource_type=ResourceType.DATASET,
            format_tags=["csv"],
            owner="bob",
            location_uri="s3://y",
        )
        results = registry.find_resources(
            resource_type=ResourceType.DATASET, tags=["csv"], owner="alice"
        )
        assert len(results) == 1
        assert results[0].name == "d1"

    def test_find_no_matches(self, registry: InMemoryRegistry):
        self._register(registry, name="d1")
        results = registry.find_resources(owner="nobody")
        assert results == []

    def test_find_all(self, registry: InMemoryRegistry):
        self._register(registry, name="d1")
        self._register(registry, name="d2", location_uri="s3://y")
        results = registry.find_resources()
        assert len(results) == 2


class TestRunCRUD:
    def test_create_and_get(self, registry: InMemoryRegistry):
        run = Run(model_id="m1", input_resource_ids=["d1"])
        created = registry.create_run(run)
        assert created.id == run.id
        retrieved = registry.get_run(run.id)
        assert retrieved.model_id == "m1"

    def test_get_nonexistent_raises(self, registry: InMemoryRegistry):
        with pytest.raises(RunNotFoundError):
            registry.get_run("nonexistent")

    def test_update_run(self, registry: InMemoryRegistry):
        run = Run(model_id="m1")
        registry.create_run(run)
        run.status = RunStatus.RUNNING
        registry.update_run(run)
        retrieved = registry.get_run(run.id)
        assert retrieved.status == RunStatus.RUNNING

    def test_update_nonexistent_raises(self, registry: InMemoryRegistry):
        run = Run(model_id="m1", id="no-such-id")
        with pytest.raises(RunNotFoundError):
            registry.update_run(run)

    def test_returned_is_copy(self, registry: InMemoryRegistry):
        run = Run(model_id="m1")
        created = registry.create_run(run)
        created.status = RunStatus.FAILED
        retrieved = registry.get_run(run.id)
        assert retrieved.status == RunStatus.REGISTERED


class TestFindRuns:
    def test_find_by_model(self, registry: InMemoryRegistry):
        registry.create_run(Run(model_id="m1"))
        registry.create_run(Run(model_id="m2"))
        results = registry.find_runs(model_id="m1")
        assert len(results) == 1
        assert results[0].model_id == "m1"

    def test_find_by_input_resource(self, registry: InMemoryRegistry):
        registry.create_run(Run(model_id="m1", input_resource_ids=["d1", "d2"]))
        registry.create_run(Run(model_id="m1", input_resource_ids=["d3"]))
        results = registry.find_runs(input_resource_id="d1")
        assert len(results) == 1

    def test_find_by_status(self, registry: InMemoryRegistry):
        r1 = Run(model_id="m1")
        r1.status = RunStatus.COMPLETED
        registry.create_run(r1)
        r2 = Run(model_id="m1")
        registry.create_run(r2)
        results = registry.find_runs(status=RunStatus.REGISTERED)
        assert len(results) == 1

    def test_find_no_matches(self, registry: InMemoryRegistry):
        registry.create_run(Run(model_id="m1"))
        results = registry.find_runs(model_id="nonexistent")
        assert results == []


class TestLineage:
    def test_get_lineage(self, registry: InMemoryRegistry):
        run = Run(
            model_id="m1",
            output_resource_ids=["out1"],
            status=RunStatus.COMPLETED,
        )
        registry.create_run(run)
        lineage = registry.get_lineage("out1")
        assert len(lineage) == 1
        assert lineage[0].model_id == "m1"

    def test_get_dependents(self, registry: InMemoryRegistry):
        run = Run(model_id="m1", input_resource_ids=["d1"])
        registry.create_run(run)
        deps = registry.get_dependents("d1")
        assert len(deps) == 1
        assert deps[0].model_id == "m1"

    def test_no_lineage(self, registry: InMemoryRegistry):
        assert registry.get_lineage("nonexistent") == []

    def test_no_dependents(self, registry: InMemoryRegistry):
        assert registry.get_dependents("nonexistent") == []
