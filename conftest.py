"""Root conftest.py — adds project root to sys.path for all tests."""
import sys
from pathlib import Path

# Ensure `src`, `ui`, etc. are importable when pytest is run from any directory.
sys.path.insert(0, str(Path(__file__).parent))
