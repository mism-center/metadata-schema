"""Enumerations for resource types, execution types, and run statuses."""

from enum import Enum


class ResourceType(str, Enum):
    DATASET = "dataset"
    MODEL = "model"
    TOOL = "tool"


class ExecutionType(str, Enum):
    DOCKER_IMAGE = "docker_image"
    PYTHON_PACKAGE = "python_package"
    CONDA_ENV = "conda_env"
    SHELL_COMMAND = "shell_command"
    NOTEBOOK = "notebook"
    OTHER = "other"


class RunStatus(str, Enum):
    REGISTERED = "registered"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
