"""Service, schema, function, and endpoint schemas"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class HTTPMethod(str, Enum):
    """HTTP methods for endpoints"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ParameterLocation(str, Enum):
    """Parameter location in HTTP request"""
    PATH = "path"
    QUERY = "query"
    BODY = "body"
    HEADER = "header"


class FunctionParameter(BaseModel):
    """Function parameter specification"""
    name: str
    type: str
    required: bool = True
    default: Optional[Any] = None
    description: Optional[str] = None


class ServiceFunction(BaseModel):
    """Service function specification"""
    id: str
    name: str = Field(..., description="Function name")
    description: Optional[str] = Field(None, description="Function description")
    parameters: List[FunctionParameter] = Field(default_factory=list)
    return_type: Optional[str] = None
    is_async: bool = True


class ServiceFunctionCreate(BaseModel):
    """Schema for creating a service function"""
    name: str
    description: Optional[str] = None
    parameters: List[FunctionParameter] = Field(default_factory=list)
    return_type: Optional[str] = None
    is_async: bool = True


class ServiceFunctionUpdate(BaseModel):
    """Schema for updating a service function"""
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[List[FunctionParameter]] = None
    return_type: Optional[str] = None
    is_async: Optional[bool] = None


class SchemaField(BaseModel):
    """Schema field specification"""
    name: str
    type: str
    required: bool = True
    default: Optional[Any] = None
    description: Optional[str] = None
    validation: Optional[Dict[str, Any]] = None


class ServiceSchema(BaseModel):
    """Service schema (DTO) specification"""
    id: str
    name: str = Field(..., description="Schema name")
    description: Optional[str] = None
    fields: List[SchemaField] = Field(default_factory=list)
    base_schema: Optional[str] = Field(None, description="Base schema to inherit from")


class ServiceSchemaCreate(BaseModel):
    """Schema for creating a service schema"""
    name: str
    description: Optional[str] = None
    fields: List[SchemaField] = Field(default_factory=list)
    base_schema: Optional[str] = None


class ServiceSchemaUpdate(BaseModel):
    """Schema for updating a service schema"""
    name: Optional[str] = None
    description: Optional[str] = None
    fields: Optional[List[SchemaField]] = None
    base_schema: Optional[str] = None


class EndpointParameter(BaseModel):
    """Endpoint parameter specification"""
    name: str
    location: ParameterLocation
    type: str
    required: bool = True
    description: Optional[str] = None


class ProviderBinding(BaseModel):
    """Provider dependency binding"""
    dependency_id: str = Field(..., description="ID of the provider dependency")


class ServiceEndpoint(BaseModel):
    """Service endpoint specification"""
    id: str
    path: str = Field(..., description="Endpoint path (e.g., /users/{id})")
    method: HTTPMethod = Field(..., description="HTTP method")
    function_name: str = Field(..., description="Service function to call")
    summary: Optional[str] = Field(None, description="Short summary for API documentation")
    description: Optional[str] = Field(None, description="Detailed description")
    tags: List[str] = Field(default_factory=list, description="Tags for grouping in API docs")
    parameters: List[EndpointParameter] = Field(default_factory=list)
    request_schema: Optional[str] = Field(None, description="Request body schema name")
    response_schema: Optional[str] = Field(None, description="Response schema name")
    status_code: int = Field(200, description="Success status code")
    middlewares: List[str] = Field(default_factory=list, description="Middleware/Dependency IDs to apply")
    providers: List[ProviderBinding] = Field(default_factory=list, description="Provider dependency bindings with parameter mappings")


class ServiceEndpointCreate(BaseModel):
    """Schema for creating a service endpoint"""
    path: str
    method: HTTPMethod
    function_name: str
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters: List[EndpointParameter] = Field(default_factory=list)
    request_schema: Optional[str] = None
    response_schema: Optional[str] = None
    status_code: int = Field(200)
    middlewares: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    providers: List[ProviderBinding] = Field(
        default_factory=list,
        description="Provider dependency bindings with parameter mappings"
    )


class ServiceEndpointUpdate(BaseModel):
    """Schema for updating a service endpoint"""
    path: Optional[str] = None
    method: Optional[HTTPMethod] = None
    function_name: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    parameters: Optional[List[EndpointParameter]] = None
    request_schema: Optional[str] = None
    response_schema: Optional[str] = None
    status_code: Optional[int] = None
    middlewares: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    providers: Optional[List[ProviderBinding]] = None


class ServiceBase(BaseModel):
    """Base schema for services"""
    name: str = Field(..., description="Service name", min_length=1)
    description: Optional[str] = None
    is_singleton: bool = Field(default=True, description="Whether service should be a singleton")


class ServiceCreate(ServiceBase):
    """Schema for creating a service"""
    pass


class ServiceUpdate(BaseModel):
    """Schema for updating a service"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_singleton: Optional[bool] = None


class Service(ServiceBase):
    """Complete service with metadata"""
    id: str
    project_id: str
    schemas: List[str] = Field(default_factory=list, description="Schema IDs")
    functions: List[str] = Field(default_factory=list, description="Function IDs")
    endpoints: List[str] = Field(default_factory=list, description="Endpoint IDs")
    created_at: str
    updated_at: str
