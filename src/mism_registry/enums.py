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


class ResourceVersionStatus(str, Enum):
    """Version lifecycle: is this the current version of the resource?"""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ResourceRegistrationStatus(str, Enum):
    """AI-augmented registration workflow: upload -> annotate -> review -> approve."""

    DRAFT = "draft"  # uploaded + titled; resource created, no metadata-package yet
    ANNOTATING = "annotating"  # agent job building the metadata-package
    ANNOTATION_FAILED = "annotation_failed"  # agent job failed; needs retry/attention
    PENDING_REVIEW = "pending_review"  # metadata-package ready for human review
    REJECTED = "rejected"  # reviewer sent it back for changes
    APPROVED = "approved"  # reviewed & approved; searchable + executable


class RunStatus(str, Enum):
    REGISTERED = "registered"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImageReviewStatus(str, Enum):
    """Dockerfile/image vetting workflow for models that ship a container recipe."""

    NOT_APPLICABLE = "not_applicable"  # no container shipped, or metadata not yet approved
    PENDING_IMAGE_CHECK = "pending_image_check"  # image submitted, awaiting IMAGE_CHECK review
    IMAGE_APPROVED = "image_approved"  # reviewed & approved; executable
    IMAGE_REJECTED = "image_rejected"  # reviewer rejected; uploader must resubmit
