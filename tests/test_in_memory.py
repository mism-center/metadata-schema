"""Tests for InMemoryRegistry."""

from datetime import date

import pytest

from mism_registry import (
    InMemoryRegistry,
    Resource,
    ResourceStatus,
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
        r = Resource(name="data", resource_type=ResourceType.DATASET, location_uri="s3://x")
        registered = registry.register_resource(r)
        assert registered.id == r.id
        retrieved = registry.get_resource(r.id)
        assert retrieved.name == "data"

    def test_get_nonexistent_raises(self, registry: InMemoryRegistry):
        with pytest.raises(ResourceNotFoundError):
            registry.get_resource("nonexistent-id")

    def test_duplicate_registration_raises(self, registry: InMemoryRegistry):
        r = Resource(name="data", resource_type=ResourceType.DATASET, location_uri="s3://x")
        registry.register_resource(r)
        with pytest.raises(DuplicateResourceError):
            registry.register_resource(r)

    def test_returned_is_copy(self, registry: InMemoryRegistry):
        r = Resource(name="data", resource_type=ResourceType.DATASET, location_uri="s3://x")
        registered = registry.register_resource(r)
        registered.name = "modified"
        retrieved = registry.get_resource(r.id)
        assert retrieved.name == "data"

    def test_update_resource(self, registry: InMemoryRegistry):
        r = Resource(name="data", resource_type=ResourceType.DATASET, location_uri="s3://x")
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
        self._register(registry, name="d2", format_tags=["fasta"], location_uri="s3://y")
        results = registry.find_resources(tags=["csv"])
        assert len(results) == 1
        assert results[0].name == "d1"

    def test_find_by_tags_subset(self, registry: InMemoryRegistry):
        self._register(registry, name="d1", format_tags=["csv", "timeseries", "extra"])
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

    def test_find_by_organisms(self, registry: InMemoryRegistry):
        self._register(registry, name="d1", organisms=["SARS-CoV-2", "Homo sapiens"])
        self._register(registry, name="d2", organisms=["HIV-1"], location_uri="s3://y")
        results = registry.find_resources(organisms=["SARS-CoV-2"])
        assert len(results) == 1
        assert results[0].name == "d1"

    def test_find_by_scales(self, registry: InMemoryRegistry):
        self._register(registry, name="d1", modeling_scales=["molecular", "cellular"])
        self._register(registry, name="d2", modeling_scales=["population"], location_uri="s3://y")
        results = registry.find_resources(scales=["molecular"])
        assert len(results) == 1
        assert results[0].name == "d1"

    def test_find_by_domains(self, registry: InMemoryRegistry):
        self._register(registry, name="d1", domains=["virology", "immunology"])
        self._register(registry, name="d2", domains=["oncology"], location_uri="s3://y")
        results = registry.find_resources(domains=["virology"])
        assert len(results) == 1
        assert results[0].name == "d1"

    def test_find_by_status(self, registry: InMemoryRegistry):
        r1 = self._register(registry, name="active")
        r2 = self._register(registry, name="archived", location_uri="s3://y")
        r2.status = ResourceStatus.ARCHIVED
        registry.update_resource(r2)
        results = registry.find_resources(status=ResourceStatus.ACTIVE)
        assert len(results) == 1
        assert results[0].name == "active"

    def test_find_by_date_published_after(self, registry: InMemoryRegistry):
        self._register(registry, name="old", date_published=date(2020, 1, 1))
        self._register(
            registry, name="new", date_published=date(2024, 6, 15), location_uri="s3://y"
        )
        results = registry.find_resources(date_published_after=date(2023, 1, 1))
        assert len(results) == 1
        assert results[0].name == "new"

    def test_find_by_date_published_before(self, registry: InMemoryRegistry):
        self._register(registry, name="old", date_published=date(2020, 1, 1))
        self._register(
            registry, name="new", date_published=date(2024, 6, 15), location_uri="s3://y"
        )
        results = registry.find_resources(date_published_before=date(2021, 1, 1))
        assert len(results) == 1
        assert results[0].name == "old"

    def test_find_by_date_range(self, registry: InMemoryRegistry):
        self._register(registry, name="old", date_published=date(2019, 1, 1))
        self._register(
            registry, name="mid", date_published=date(2022, 6, 1), location_uri="s3://y"
        )
        self._register(
            registry, name="new", date_published=date(2025, 1, 1), location_uri="s3://z"
        )
        results = registry.find_resources(
            date_published_after=date(2021, 1, 1),
            date_published_before=date(2023, 12, 31),
        )
        assert len(results) == 1
        assert results[0].name == "mid"

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


class TestVersionMethods:
    def test_get_latest_version_single(self, registry: InMemoryRegistry):
        r = Resource(name="data", resource_type=ResourceType.DATASET, location_uri="s3://x")
        registry.register_resource(r)
        latest = registry.get_latest_version(r.id)
        assert latest is not None
        assert latest.id == r.id

    def test_get_latest_version_chain(self, registry: InMemoryRegistry):
        v1 = Resource(
            name="data",
            resource_type=ResourceType.DATASET,
            location_uri="s3://v1",
            status=ResourceStatus.SUPERSEDED,
        )
        v2 = Resource(
            name="data",
            resource_type=ResourceType.DATASET,
            location_uri="s3://v2",
            new_version_of=v1.id,
        )
        v1.superseded_by = v2.id
        registry.register_resource(v1)
        registry.register_resource(v2)
        latest = registry.get_latest_version(v1.id)
        assert latest is not None
        assert latest.id == v2.id

    def test_get_latest_version_nonexistent(self, registry: InMemoryRegistry):
        assert registry.get_latest_version("nonexistent") is None

    def test_get_version_history_single(self, registry: InMemoryRegistry):
        r = Resource(name="data", resource_type=ResourceType.DATASET, location_uri="s3://x")
        registry.register_resource(r)
        history = registry.get_version_history(r.id)
        assert len(history) == 1
        assert history[0].id == r.id

    def test_get_version_history_chain(self, registry: InMemoryRegistry):
        v1 = Resource(
            name="data",
            resource_type=ResourceType.DATASET,
            location_uri="s3://v1",
            status=ResourceStatus.SUPERSEDED,
        )
        v2 = Resource(
            name="data",
            resource_type=ResourceType.DATASET,
            location_uri="s3://v2",
            new_version_of=v1.id,
            status=ResourceStatus.SUPERSEDED,
        )
        v3 = Resource(
            name="data",
            resource_type=ResourceType.DATASET,
            location_uri="s3://v3",
            new_version_of=v2.id,
        )
        v1.superseded_by = v2.id
        v2.superseded_by = v3.id
        registry.register_resource(v1)
        registry.register_resource(v2)
        registry.register_resource(v3)

        # Can query from any point in the chain
        for rid in [v1.id, v2.id, v3.id]:
            history = registry.get_version_history(rid)
            assert len(history) == 3
            assert history[0].id == v1.id
            assert history[1].id == v2.id
            assert history[2].id == v3.id

    def test_get_version_history_nonexistent(self, registry: InMemoryRegistry):
        assert registry.get_version_history("nonexistent") == []
