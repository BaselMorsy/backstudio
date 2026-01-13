"""Middleware schemas"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class MiddlewareType(str, Enum):
    """Middleware types"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CORS = "cors"
    RATE_LIMITING = "rate_limiting"
    LOGGING = "logging"
    COMPRESSION = "compression"
    CUSTOM = "custom"


class MiddlewareBase(BaseModel):
    """Base schema for middleware"""
    name: str = Field(..., description="Middleware name", min_length=1)
    type: MiddlewareType = Field(..., description="Middleware type")
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict, description="Middleware configuration")
    enabled: bool = Field(default=True, description="Whether middleware is enabled")
    order: int = Field(default=0, description="Execution order (lower executes first)")


class MiddlewareCreate(MiddlewareBase):
    """Schema for creating a middleware"""
    pass


class MiddlewareUpdate(BaseModel):
    """Schema for updating a middleware"""
    name: Optional[str] = None
    type: Optional[MiddlewareType] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


class Middleware(MiddlewareBase):
    """Complete middleware with metadata"""
    id: str
    project_id: str
    created_at: str
    updated_at: str
