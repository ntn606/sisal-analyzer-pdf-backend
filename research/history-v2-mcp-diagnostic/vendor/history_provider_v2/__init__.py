"""Offline football histories; no transport, credentials or backend imports."""

from .provider import Dataset, InputError, Snapshot, build_history, load_snapshots

__all__ = ['Dataset', 'InputError', 'Snapshot', 'build_history', 'load_snapshots']
