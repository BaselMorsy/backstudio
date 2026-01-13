"""ID generation utilities"""

import uuid
from typing import Literal


def generate_id(prefix: str = "") -> str:
    """
    Generate unique ID with optional prefix.

    Args:
        prefix: Optional prefix for the ID (e.g., 'proj', 'model', 'svc')

    Returns:
        Unique identifier string

    Example:
        >>> generate_id('proj')
        'proj_a1b2c3d4e5f6...'
    """
    unique_id = uuid.uuid4().hex[:12]
    return f"{prefix}_{unique_id}" if prefix else unique_id


def generate_project_id() -> str:
    """Generate project ID"""
    return generate_id('proj')


def generate_model_id() -> str:
    """Generate data model ID"""
    return generate_id('model')


def generate_service_id() -> str:
    """Generate service ID"""
    return generate_id('svc')


def generate_schema_id() -> str:
    """Generate schema ID"""
    return generate_id('schema')


def generate_function_id() -> str:
    """Generate function ID"""
    return generate_id('func')


def generate_endpoint_id() -> str:
    """Generate endpoint ID"""
    return generate_id('ep')


def generate_middleware_id() -> str:
    """Generate middleware ID"""
    return generate_id('mw')


def generate_dependency_id() -> str:
    """Generate dependency ID"""
    return generate_id('dep')


def generate_relation_id() -> str:
    """Generate relation ID"""
    return generate_id('rel')
