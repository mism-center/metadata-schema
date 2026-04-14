"""Tests for the Run dataclass."""

import uuid
from datetime import timezone

from mism_registry import Run, RunEnvironment, RunStatus


class TestRun:
    def test_auto_uuid(self):
        r = Run(model_id="some-model-id")
        uuid.UUID(r.id)

    def test_defaults(self):
        r = Run(model_id="m1")
        assert r.model_id == "m1"
        assert r.status == RunStatus.REGISTERED
        assert r.model_version == ""
        assert r.input_resource_ids == []
        assert r.output_resource_ids == []
        assert r.parameters == {}
        assert r.environment is None
        assert r.started_at is None
        assert r.completed_at is None
        assert r.error_message == ""
        assert r.log_uri == ""
        assert r.triggered_by == ""
        assert r.notes == ""

    def test_created_at_utc(self):
        r = Run(model_id="m1")
        assert r.created_at.tzinfo == timezone.utc

    def test_with_environment(self):
        env = RunEnvironment(platform="helx", hardware_description="4xA100")
        r = Run(model_id="m1", environment=env)
        assert r.environment is not None
        assert r.environment.platform == "helx"

    def test_with_parameters(self):
        r = Run(
            model_id="m1",
            parameters={"threshold": 0.03, "batch_size": 32},
        )
        assert r.parameters["threshold"] == 0.03

    def test_mutable_status(self):
        r = Run(model_id="m1")
        r.status = RunStatus.RUNNING
        assert r.status == RunStatus.RUNNING

    def test_input_output_ids(self):
        r = Run(
            model_id="m1",
            input_resource_ids=["d1", "d2"],
            output_resource_ids=["d3"],
        )
        assert r.input_resource_ids == ["d1", "d2"]
        assert r.output_resource_ids == ["d3"]

    def test_model_version_denormalized(self):
        r = Run(model_id="m1", model_version="2.0.0")
        assert r.model_version == "2.0.0"
