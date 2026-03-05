"""Tests for lineage tracing across multi-hop pipelines."""

from mism_registry import (
    ExecutionType,
    InMemoryRegistry,
    IOSlot,
    IOSpec,
    Resource,
    ResourceType,
    complete_run,
    get_dependents,
    get_lineage,
    prepare_run,
    register_dataset,
    register_model,
    start_run,
)


def _make_model(registry, name="model", input_tags=(), output_tags=()):
    """Helper: register a model with optional IOSpec."""
    io_spec = IOSpec(
        inputs=tuple(IOSlot(name=f"in_{i}", tags=t) for i, t in enumerate(input_tags)),
        outputs=tuple(IOSlot(name=f"out_{i}", tags=t) for i, t in enumerate(output_tags)),
    ) if input_tags or output_tags else IOSpec()
    return register_model(
        registry,
        name=name,
        location_uri=f"docker://{name}:v1",
        execution_type=ExecutionType.DOCKER,
        io_spec=io_spec,
    )


class TestLinearPipeline:
    """D1 -> M1 -> D2 -> M2 -> D3"""

    def test_full_chain(self):
        reg = InMemoryRegistry()

        # Register initial dataset
        d1 = register_dataset(
            reg, name="D1", location_uri="s3://d1", format_tags=["fasta"]
        )

        # Register models
        m1 = _make_model(reg, "M1", input_tags=[("fasta",)], output_tags=[("csv",)])
        m2 = _make_model(reg, "M2", input_tags=[("csv",)], output_tags=[("json",)])

        # Run 1: D1 -> M1 -> D2
        run1 = prepare_run(reg, model_id=m1.id, input_resource_ids=[d1.id])
        run1 = start_run(reg, run_id=run1.id)
        d2 = Resource(
            name="D2",
            resource_type=ResourceType.DATASET,
            location_uri="s3://d2",
            format_tags=["csv"],
        )
        run1 = complete_run(reg, run_id=run1.id, output_resources=[d2])
        d2_id = run1.output_resource_ids[0]

        # Run 2: D2 -> M2 -> D3
        run2 = prepare_run(reg, model_id=m2.id, input_resource_ids=[d2_id])
        run2 = start_run(reg, run_id=run2.id)
        d3 = Resource(
            name="D3",
            resource_type=ResourceType.DATASET,
            location_uri="s3://d3",
            format_tags=["json"],
        )
        run2 = complete_run(reg, run_id=run2.id, output_resources=[d3])
        d3_id = run2.output_resource_ids[0]

        # Verify lineage of D3 (direct producer)
        lineage_d3 = get_lineage(reg, d3_id)
        assert len(lineage_d3) == 1
        assert lineage_d3[0].model_id == m2.id

        # Verify lineage of D2
        lineage_d2 = get_lineage(reg, d2_id)
        assert len(lineage_d2) == 1
        assert lineage_d2[0].model_id == m1.id

        # Verify dependents of D1
        deps_d1 = get_dependents(reg, d1.id)
        assert len(deps_d1) == 1
        assert deps_d1[0].model_id == m1.id

        # Verify dependents of D2 (consumed by M2)
        deps_d2 = get_dependents(reg, d2_id)
        assert len(deps_d2) == 1
        assert deps_d2[0].model_id == m2.id

        # D1 has no lineage (it's the origin)
        assert get_lineage(reg, d1.id) == []

        # D3 has no dependents (it's the terminal)
        assert get_dependents(reg, d3_id) == []


class TestDiamondPattern:
    """D1 is consumed by both Run1 and Run2."""

    def test_shared_input(self):
        reg = InMemoryRegistry()
        d1 = register_dataset(
            reg, name="D1", location_uri="s3://d1", format_tags=["csv"]
        )
        m1 = _make_model(reg, "M1")
        m2 = _make_model(reg, "M2")

        prepare_run(reg, model_id=m1.id, input_resource_ids=[d1.id])
        prepare_run(reg, model_id=m2.id, input_resource_ids=[d1.id])

        deps = get_dependents(reg, d1.id)
        assert len(deps) == 2
        model_ids = {d.model_id for d in deps}
        assert model_ids == {m1.id, m2.id}


class TestMultipleInputs:
    """A run that takes multiple input datasets."""

    def test_multi_input_run(self):
        reg = InMemoryRegistry()
        d1 = register_dataset(
            reg, name="D1", location_uri="s3://d1", format_tags=["fasta"]
        )
        d2 = register_dataset(
            reg, name="D2", location_uri="s3://d2", format_tags=["pdb"]
        )
        m = _make_model(
            reg, "Multi-Input Model",
            input_tags=[("fasta",), ("pdb",)],
        )
        run = prepare_run(
            reg, model_id=m.id, input_resource_ids=[d1.id, d2.id]
        )
        assert len(run.input_resource_ids) == 2

        # Both D1 and D2 are dependencies of this run
        deps_d1 = get_dependents(reg, d1.id)
        deps_d2 = get_dependents(reg, d2.id)
        assert len(deps_d1) == 1
        assert len(deps_d2) == 1
        assert deps_d1[0].id == deps_d2[0].id


class TestMultipleOutputs:
    """A run that produces multiple output datasets."""

    def test_multi_output_run(self):
        reg = InMemoryRegistry()
        d1 = register_dataset(
            reg, name="D1", location_uri="s3://d1", format_tags=["csv"]
        )
        m = _make_model(reg, "Multi-Output Model")

        run = prepare_run(reg, model_id=m.id, input_resource_ids=[d1.id])
        run = start_run(reg, run_id=run.id)

        out1 = Resource(
            name="Out1",
            resource_type=ResourceType.DATASET,
            location_uri="s3://out1",
        )
        out2 = Resource(
            name="Out2",
            resource_type=ResourceType.DATASET,
            location_uri="s3://out2",
        )
        completed = complete_run(
            reg, run_id=run.id, output_resources=[out1, out2]
        )
        assert len(completed.output_resource_ids) == 2

        # Both outputs trace back to the same run
        for oid in completed.output_resource_ids:
            lineage = get_lineage(reg, oid)
            assert len(lineage) == 1
            assert lineage[0].id == completed.id
