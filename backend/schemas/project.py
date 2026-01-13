"""Project state schemas"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class Framework(str, Enum):
    """Supported backend frameworks - Python only"""
    FASTAPI = "fastapi"


class ProjectBase(BaseModel):
    """Base schema for project information"""
    name: str = Field(..., description="Project name", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Project description")
    version: str = Field(default="1.0.0", description="Project version")


class ProjectCreate(ProjectBase):
    """Schema for creating a new project"""
    framework: Framework = Field(default=Framework.FASTAPI, description="Target framework")


class ProjectUpdate(BaseModel):
    """Schema for updating project details"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    version: Optional[str] = None
    framework: Optional[Framework] = None


class ProjectSummary(BaseModel):
    """Summary schema for project listings"""
    id: str = Field(..., description="Project unique identifier")
    name: str
    version: str
    framework: Framework
    created_at: str
    updated_at: str


class ProjectState(BaseModel):
    """Complete project state including all specifications"""
    id: str
    name: str
    description: Optional[str] = None
    version: str
    framework: Framework

    # References to other components by ID
    models: List[str] = Field(default_factory=list, description="Data model IDs")
    services: List[str] = Field(default_factory=list, description="Service IDs")
    middlewares: List[str] = Field(default_factory=list, description="Middleware IDs")
    dependencies: List[str] = Field(default_factory=list, description="Dependency IDs")

    # Configuration
    database_config: Optional[Dict[str, Any]] = None
    framework_config: Optional[Dict[str, Any]] = None
    security_config: Optional[Dict[str, Any]] = None

    # Metadata
    created_at: str
    updated_at: str
    checksum: str = Field(..., description="SHA256 checksum of the normalized state")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "proj_123",
                "name": "MyAPI",
                "version": "1.0.0",
                "framework": "fastapi",
                "models": ["model_1", "model_2"],
                "checksum": "abc123..."
            }
        }
