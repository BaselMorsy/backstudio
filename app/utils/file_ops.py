"""File operation utilities"""

import re
from pathlib import Path

_UNSAFE_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def ensure_directory(path: Path) -> Path:
    """Ensure the directory exists (creating parents as needed) and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_dir_name(name: str) -> str:
    """Turn free text (a project name) into a single, safe directory-name segment.

    Path separators and characters invalid in file names become "_", and leading/trailing
    spaces and dots are dropped so the result can never be "." or "..". Raises ValueError
    if nothing usable is left.
    """
    cleaned = _UNSAFE_PATH_CHARS.sub("_", name).strip(" .")
    if not cleaned:
        raise ValueError(f"'{name}' cannot be used as a directory name")
    return cleaned
