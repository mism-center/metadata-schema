"""How to use entry points when preparing a run.

Flow: a model declares entry_points (each with typed Arguments) and one or
more container recipes. The API selects an entry point BY INDEX (never by a
caller-supplied command string — injection defense) and supplies argument
VALUES keyed by the declared argument names. prepare_run validates those
values, denormalizes a container onto the run, and stores the entry point.
The execution layer then renders a safe command via EntryPoint.to_cli().
"""

import pytest

from mism_registry import (
    ExecutionType,
    ImageReviewStatus,
    InMemoryRegistry,
    ResourceRegistrationStatus,
    prepare_run,
    register_model,
    set_image_review_status,
    set_registration_status,
)
from mism_registry.errors import ValidationError
from mism_registry.types import Argument, Container, EntryPoint


def _approve(registry, resource):
    """Walk DRAFT -> APPROVED so the model is executable."""
    for status in (
        ResourceRegistrationStatus.ANNOTATING,
        ResourceRegistrationStatus.PENDING_REVIEW,
        ResourceRegistrationStatus.APPROVED,
    ):
        resource = set_registration_status(registry, resource_id=resource.id, target=status)
    return resource


@pytest.fixture()
def model_with_entrypoints(registry: InMemoryRegistry):
    """Approved model: two entry points (flag-based + positional) + a container."""
    model = register_model(
        registry,
        name="Chemotaxis",
        location_uri="git+https://github.com/org/chemo@v1",
        execution_type=ExecutionType.DOCKER,
        version="1.0.0",
        containers=[Container(kind="docker", file="Dockerfile", image_name="chemo:1")],
        entry_points=[
            # index 0 — option flags
            EntryPoint(
                command="python chemotaxis/composites/chemotaxis_flagella.py",
                arguments=(
                    Argument(name="--variable", data_type="bool", default=False),
                    Argument(name="--flagella", data_type="int", default=5),
                ),
            ),
            # index 1 — a required positional constrained by enums
            EntryPoint(
                command="python chemotaxis/experiments/paper_experiments.py <experiment_id>",
                arguments=(
                    Argument(
                        name="experiment_id",
                        data_type="str",
                        position=1,
                        enums=("7b", "fig3"),
                        default=None,
                    ),
                ),
            ),
        ],
    )
    model = _approve(registry, model)
    # This fixture ships a Container, so the image-check gate also needs
    # clearing before prepare_run will allow it (mirrors an already-vetted,
    # ready-to-run model — these tests are about entry-point rendering, not
    # about the image-review workflow itself).
    set_image_review_status(
        registry, resource_id=model.id, target=ImageReviewStatus.PENDING_IMAGE_CHECK
    )
    return set_image_review_status(
        registry,
        resource_id=model.id,
        target=ImageReviewStatus.IMAGE_APPROVED,
        reviewed_by="test-reviewer",
    )


class TestEntryPointsInRuns:
    def test_select_entrypoint_inherits_container(self, registry, model_with_entrypoints):
        run = prepare_run(
            registry,
            model_id=model_with_entrypoints.id,
            input_resource_ids=[],
            entrypoint_index=0,
        )
        # entry point stored on the run; container denormalized from the model
        assert run.entrypoint.command.endswith("chemotaxis_flagella.py")
        assert run.container == Container(kind="docker", file="Dockerfile", image_name="chemo:1")

    def test_render_cli_uses_defaults(self, registry, model_with_entrypoints):
        run = prepare_run(
            registry,
            model_id=model_with_entrypoints.id,
            input_resource_ids=[],
            entrypoint_index=0,
        )
        # bool default False -> omitted; int default 5 -> emitted
        assert run.entrypoint.to_cli(run.parameters) == (
            "python chemotaxis/composites/chemotaxis_flagella.py --flagella 5"
        )

    def test_arguments_override_defaults(self, registry, model_with_entrypoints):
        run = prepare_run(
            registry,
            model_id=model_with_entrypoints.id,
            input_resource_ids=[],
            entrypoint_index=0,
            arguments={"--variable": True, "--flagella": 3},
        )
        assert run.entrypoint.to_cli(run.parameters) == (
            "python chemotaxis/composites/chemotaxis_flagella.py --variable --flagella 3"
        )

    def test_positional_with_enum(self, registry, model_with_entrypoints):
        run = prepare_run(
            registry,
            model_id=model_with_entrypoints.id,
            input_resource_ids=[],
            entrypoint_index=1,
            arguments={"experiment_id": "7b"},
        )
        # <experiment_id> placeholder stripped; value appended positionally
        assert run.entrypoint.to_cli(run.parameters) == (
            "python chemotaxis/experiments/paper_experiments.py 7b"
        )

    def test_no_entrypoint_still_inherits_container(self, registry, model_with_entrypoints):
        run = prepare_run(
            registry,
            model_id=model_with_entrypoints.id,
            input_resource_ids=[],
        )
        assert run.entrypoint is None
        assert run.container.image_name == "chemo:1"

    # ── validation / injection defense ──────────────────────────────────

    def test_value_with_shell_metachars_is_quoted(self, registry, model_with_entrypoints):
        # A path value containing a space + shell chars is shlex-quoted, not
        # interpreted — the caller cannot break out of the argument slot.
        run = prepare_run(
            registry,
            model_id=model_with_entrypoints.id,
            input_resource_ids=[],
            entrypoint_index=0,
            arguments={"--flagella": "5; rm -rf /"},
        )
        assert "'5; rm -rf /'" in run.entrypoint.to_cli(run.parameters)

    def test_unknown_argument_rejected(self, registry, model_with_entrypoints):
        with pytest.raises(ValidationError, match="Unknown argument"):
            prepare_run(
                registry,
                model_id=model_with_entrypoints.id,
                input_resource_ids=[],
                entrypoint_index=0,
                arguments={"--bogus": 1},
            )

    def test_enum_violation_rejected(self, registry, model_with_entrypoints):
        with pytest.raises(ValidationError, match="not in allowed values"):
            prepare_run(
                registry,
                model_id=model_with_entrypoints.id,
                input_resource_ids=[],
                entrypoint_index=1,
                arguments={"experiment_id": "nope"},
            )

    def test_missing_positional_rejected(self, registry, model_with_entrypoints):
        with pytest.raises(ValidationError, match="Positional argument"):
            prepare_run(
                registry,
                model_id=model_with_entrypoints.id,
                input_resource_ids=[],
                entrypoint_index=1,
            )

    def test_out_of_range_index_rejected(self, registry, model_with_entrypoints):
        with pytest.raises(ValidationError, match="out of range"):
            prepare_run(
                registry,
                model_id=model_with_entrypoints.id,
                input_resource_ids=[],
                entrypoint_index=99,
            )

    def test_arguments_without_entrypoint_rejected(self, registry, model_with_entrypoints):
        with pytest.raises(ValidationError, match="no entrypoint_index"):
            prepare_run(
                registry,
                model_id=model_with_entrypoints.id,
                input_resource_ids=[],
                arguments={"--flagella": 3},
            )
