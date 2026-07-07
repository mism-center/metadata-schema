"""Enumerations for resource types, execution types, resource statuses, and run statuses."""

from enum import Enum


class ResourceType(str, Enum):
    DATASET = "dataset"
    MODEL = "model"
    TOOL = "tool"


class ExecutionType(str, Enum):
    DOCKER = "docker"
    CONDA = "conda"
    PIP = "pip"
    PYTHON = "python"
    R = "r"
    BINARY = "binary"
    HUGGINGFACE = "huggingface"
    NOTEBOOK = "notebook"
    # schema.md execution.environment_kind additions
    SINGULARITY = "singularity"
    NEXTFLOW = "nextflow"
    SNAKEMAKE = "snakemake"
    JUPYTER = "jupyter"
    NATIVE = "native"
    OTHER = "other"


class ResourceStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class RunStatus(str, Enum):
    REGISTERED = "registered"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
