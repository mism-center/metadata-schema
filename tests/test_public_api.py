"""Tests for public API surface and imports."""

import mism_registry


class TestPublicAPI:
    def test_version_exists(self):
        assert isinstance(mism_registry.__version__, str)
        assert "." in mism_registry.__version__

    def test_all_names_importable(self):
        for name in mism_registry.__all__:
            assert hasattr(mism_registry, name), f"{name} not found in mism_registry"

    def test_in_memory_registry_satisfies_protocol(self):
        reg = mism_registry.InMemoryRegistry()
        assert isinstance(reg, mism_registry.Registry)

    def test_all_enums_importable(self):
        assert mism_registry.ResourceType.DATASET is not None
        assert mism_registry.ExecutionType.DOCKER is not None
        assert mism_registry.ResourceStatus.ACTIVE is not None
        assert mism_registry.RunStatus.REGISTERED is not None

    def test_all_types_importable(self):
        assert mism_registry.Author is not None
        assert mism_registry.Publication is not None
        assert mism_registry.IOSlot is not None
        assert mism_registry.IOSpec is not None
        assert mism_registry.RunEnvironment is not None
        assert mism_registry.Resource is not None
        assert mism_registry.Run is not None

    def test_all_errors_importable(self):
        assert issubclass(mism_registry.ResourceNotFoundError, mism_registry.MismRegistryError)
        assert issubclass(mism_registry.RunNotFoundError, mism_registry.MismRegistryError)
        assert issubclass(mism_registry.ValidationError, mism_registry.MismRegistryError)
        assert issubclass(mism_registry.DuplicateResourceError, mism_registry.MismRegistryError)
        assert issubclass(mism_registry.IOSpecMismatchError, mism_registry.MismRegistryError)
        assert issubclass(
            mism_registry.InvalidStateTransitionError, mism_registry.MismRegistryError
        )

    def test_all_operations_are_callable(self):
        ops = [
            "register_dataset",
            "register_model",
            "create_new_version",
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
        ]
        for op in ops:
            assert callable(getattr(mism_registry, op)), f"{op} is not callable"
