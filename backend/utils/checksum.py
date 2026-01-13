"""Checksum utilities for deterministic state hashing"""

import hashlib
import json
from typing import Any, Dict


def normalize_dict(data: Dict[str, Any]) -> str:
    """
    Normalize a dictionary to a canonical JSON string for checksum generation.

    Ensures deterministic serialization by:
    - Sorting all dictionary keys
    - Removing whitespace
    - Using consistent separators

    Args:
        data: Dictionary to normalize

    Returns:
        Canonical JSON string representation
    """
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def compute_checksum(data: Dict[str, Any]) -> str:
    """
    Compute SHA256 checksum of normalized dictionary data.

    The checksum is deterministic - same input always produces same checksum.
    This allows verification that project specs haven't changed.

    Args:
        data: Dictionary containing project state (without checksum field)

    Returns:
        Hexadecimal SHA256 checksum string

    Example:
        >>> state = {"name": "MyProject", "version": "1.0.0"}
        >>> checksum = compute_checksum(state)
        >>> len(checksum)
        64
    """
    # Create a copy without the checksum field to avoid circular dependency
    data_copy = {k: v for k, v in data.items() if k != 'checksum'}

    # Normalize to canonical JSON string
    canonical_json = normalize_dict(data_copy)

    # Compute SHA256 hash
    hash_object = hashlib.sha256(canonical_json.encode('utf-8'))
    return hash_object.hexdigest()


def verify_checksum(data: Dict[str, Any], expected_checksum: str) -> bool:
    """
    Verify that data matches expected checksum.

    Args:
        data: Dictionary to verify
        expected_checksum: Expected checksum value

    Returns:
        True if checksum matches, False otherwise

    Example:
        >>> state = {"name": "MyProject", "version": "1.0.0", "checksum": "abc..."}
        >>> verify_checksum(state, state["checksum"])
        True
    """
    computed = compute_checksum(data)
    return computed == expected_checksum
