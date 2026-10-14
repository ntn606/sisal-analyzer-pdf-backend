"""Football Evidence & Validation V1: isolated, offline and diagnostic."""

from .validation import validate_dossier
from .register import Registry
from .evaluator import evaluate

__all__ = ["validate_dossier", "Registry", "evaluate"]
