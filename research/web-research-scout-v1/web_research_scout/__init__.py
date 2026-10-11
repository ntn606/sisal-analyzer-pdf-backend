"""Cache-only Web Research Scout. Importing this package never starts acquisition."""

from .probe import DiagnosticProbe

__all__ = ["DiagnosticProbe"]
