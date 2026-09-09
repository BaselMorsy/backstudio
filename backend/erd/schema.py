"""Pydantic schema for the YAML ERD configuration consumed by the backstudio CLI."""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.schemas.data import Cardinality, LazyStrategy, ModelField

ALL_ACTIONS = ["create", "list", "read", "update", "delete"]


class CliDatabaseType(str, Enum):
    """Database backends the CLI's SQLAlchemy code generation supports."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class ProjectMeta(BaseModel):
    name: str = Field(..., min_length=1)
    version: str = "1.0.0"
    description: Optional[str] = None


class DatabaseSpec(BaseModel):
    type: CliDatabaseType
    host: Optional[str] = "localhost"
    port: Optional[int] = None
    database_name: str
    username: Optional[str] = None
    use_env_vars: bool = True
    pool_size: int = 10
    echo: bool = False
    async_mode: bool = False


class JWTSpec(BaseModel):
    secret_env_var: str = "JWT_SECRET"
    algorithm: str = "HS256"
    expiration_minutes: int = 30


class AuthSpec(BaseModel):
    enabled: bool = False
    jwt: JWTSpec = Field(default_factory=JWTSpec)


class RBACSpec(BaseModel):
    enabled: bool = False
    roles: List[str] = Field(default_factory=list)
    default_permissions: Dict[str, List[str]] = Field(default_factory=dict)

    @field_validator("default_permissions")
    @classmethod
    def actions_are_known(cls, v: Dict[str, List[str]]) -> Dict[str, List[str]]:
        for action in v:
            if action not in ALL_ACTIONS:
                raise ValueError(
                    f"rbac.default_permissions: unknown action '{action}' (expected one of {ALL_ACTIONS})"
                )
        return v


class RelationshipDecl(BaseModel):
    """A relationship declared from one entity to another.

    Only one side needs to declare it; `translate.py` fills in the other side.
    """
    name: str
    cardinality: Cardinality
    target: str
    attribute: Optional[str] = None
    target_attribute: Optional[str] = None
    foreign_key_column: Optional[str] = None
    nullable: bool = True
    unique: bool = False
    ondelete: Optional[str] = None
    lazy: Optional[LazyStrategy] = None
    cascade: Optional[str] = None
    association_table: Optional[str] = None


class ServiceDecl(BaseModel):
    """Assigns a set of entities to a named service/module."""
    name: str = Field(..., min_length=1)
    entities: List[str] = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def name_is_valid_python_identifier(cls, v: str) -> str:
        if not (v.isidentifier() and v.islower()):
            raise ValueError(
                f"services: service name '{v}' must be a valid lowercase Python identifier "
                "(letters, digits, underscores; not starting with a digit) - it becomes the "
                "generated modules/<name>/ directory and function-name segment"
            )
        return v


class EndpointRBAC(BaseModel):
    create: Optional[List[str]] = None
    list: Optional[List[str]] = None
    read: Optional[List[str]] = None
    update: Optional[List[str]] = None
    delete: Optional[List[str]] = None


class EndpointSpec(BaseModel):
    enabled: List[str] = Field(default_factory=lambda: list(ALL_ACTIONS))
    base_path: Optional[str] = None
    tags: Optional[List[str]] = None
    rbac: Optional[EndpointRBAC] = None

    @field_validator("enabled")
    @classmethod
    def actions_are_known(cls, v: List[str]) -> List[str]:
        for action in v:
            if action not in ALL_ACTIONS:
                raise ValueError(f"endpoints.enabled: unknown action '{action}' (expected one of {ALL_ACTIONS})")
        return v


class EntitySpec(BaseModel):
    name: str = Field(..., min_length=1)
    table_name: Optional[str] = None
    fields: List[ModelField] = Field(default_factory=list)
    relationships: List[RelationshipDecl] = Field(default_factory=list)
    endpoints: EndpointSpec = Field(default_factory=EndpointSpec)


class ERDConfig(BaseModel):
    project: ProjectMeta
    database: DatabaseSpec
    auth: AuthSpec = Field(default_factory=AuthSpec)
    rbac: RBACSpec = Field(default_factory=RBACSpec)
    entities: List[EntitySpec] = Field(default_factory=list)
    services: List[ServiceDecl] = Field(default_factory=list)
