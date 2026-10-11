"""Diagnostic wrapper; no production imports or automatic network requests."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from .service import ProbeService
__all__=['ProbeService']
