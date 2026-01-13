"""Dependency injection schemas"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class DependencyType(str, Enum):
    """Dependency injection types"""
    GUARD = "guard"  # Decorator-level dependencies (e.g., auth guards)
    PROVIDER = "provider"  # Function argument dependencies (e.g., db session, current user)


class DependencyScope(str, Enum):
    """Dependency lifecycle scope"""
    SINGLETON = "singleton"  # Single instance for entire application
    REQUEST = "request"  # New instance per request
    TRANSIENT = "transient"  # New instance each time injected


class DependencyBase(BaseModel):
    """Base schema for dependency injection"""
    name: str = Field(..., description="Dependency name", min_length=1)
    type: DependencyType = Field(..., description="Dependency type (guard or provider)")
    description: Optional[str] = None
    scope: DependencyScope = Field(default=DependencyScope.REQUEST, description="Dependency lifecycle scope")
    function_name: str = Field(..., description="Name of the function that provides this dependency")
    return_type: Optional[str] = Field(None, description="Return type of the dependency (e.g., 'User', 'int', 'str')")
    return_field: Optional[str] = Field(None, description="Specific field to extract from return type (e.g., 'id' extracts User.id)")
    parameters: List[Dict[str, Any]] = Field(default_factory=list, description="Function parameters")
    is_async: bool = Field(default=True, description="Whether the dependency function is async")


class DependencyCreate(DependencyBase):
    """Schema for creating a dependency"""
    pass


class DependencyUpdate(BaseModel):
    """Schema for updating a dependency"""
    name: Optional[str] = None
    type: Optional[DependencyType] = None
    description: Optional[str] = None
    scope: Optional[DependencyScope] = None
    function_name: Optional[str] = None
    return_type: Optional[str] = None
    return_field: Optional[str] = None
    parameters: Optional[List[Dict[str, Any]]] = None
    is_async: Optional[bool] = None


class Dependency(DependencyBase):
    """Complete dependency with metadata"""
    id: str
    project_id: str
    created_at: str
    updated_at: str
