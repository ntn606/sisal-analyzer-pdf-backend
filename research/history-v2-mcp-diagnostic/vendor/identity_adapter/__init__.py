"""Isolated identity adapter; pinned unchanged History Provider V2, no network."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
from .core import probe

__all__ = ['probe']
