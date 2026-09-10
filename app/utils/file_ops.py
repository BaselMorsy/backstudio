"""File operation utilities"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


def ensure_directory(path: Path) -> Path:
    """
    Ensure directory exists, create if it doesn't.

    Args:
        path: Directory path to ensure

    Returns:
        The path object
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json_file(file_path: Path) -> Dict[str, Any]:
    """
    Read JSON file and return parsed data.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data as dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json_file(file_path: Path, data: Dict[str, Any], indent: int = 2) -> None:
    """
    Write data to JSON file with pretty formatting.

    Args:
        file_path: Path to write JSON file
        data: Data to serialize
        indent: Number of spaces for indentation
    """
    ensure_directory(file_path.parent)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def delete_directory(path: Path) -> None:
    """
    Recursively delete directory and all contents.

    Args:
        path: Directory path to delete
    """
    if path.exists() and path.is_dir():
        shutil.rmtree(path)


def get_timestamp() -> str:
    """
    Get current timestamp in ISO format.

    Returns:
        ISO formatted timestamp string
    """
    return datetime.utcnow().isoformat() + 'Z'


def copy_directory(src: Path, dst: Path, exclude_patterns: Optional[list] = None) -> None:
    """
    Copy directory tree with optional exclusions.

    Args:
        src: Source directory
        dst: Destination directory
        exclude_patterns: List of patterns to exclude
    """
    exclude_patterns = exclude_patterns or []
    ensure_directory(dst)

    for item in src.rglob('*'):
        # Skip excluded items
        if any(pattern in str(item) for pattern in exclude_patterns):
            continue

        relative_path = item.relative_to(src)
        dest_path = dst / relative_path

        if item.is_dir():
            ensure_directory(dest_path)
        else:
            ensure_directory(dest_path.parent)
            shutil.copy2(item, dest_path)
