"""File operation utilities"""

from pathlib import Path


def ensure_directory(path: Path) -> Path:
    """Ensure the directory exists (creating parents as needed) and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
