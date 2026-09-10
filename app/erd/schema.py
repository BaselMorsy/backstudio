"""Pydantic schema for the YAML ERD configuration consumed by the backstudio CLI."""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Cardinality(str, Enum):
	"""Relationship cardinality types"""
	ONE_TO_MANY = "one-to-many"
	MANY_TO_ONE = "many-to-one"
	ONE_TO_ONE = "one-to-one"
	MANY_TO_MANY = "many-to-many"


class LazyStrategy(str, Enum):
	"""SQLAlchemy lazy loading strategies"""
	SELECT = "select"
	JOINED = "joined"
	SELECTIN = "selectin"
	SUBQUERY = "subquery"
	RAISE = "raise"


class FieldType(str, Enum):
	"""Data model field types"""
	STRING = "string"
	INTEGER = "integer"
	FLOAT = "float"
	BOOLEAN = "boolean"
	DATETIME = "datetime"
	DATE = "date"
	TEXT = "text"
	JSON = "json"
	UUID = "uuid"


class ModelField(BaseModel):
	"""Data model field specification"""
	name: str = Field(..., description="Field name")
	type: FieldType = Field(..., description="Field data type")
	nullable: bool = Field(default=True, description="Whether field can be null")
	unique: bool = Field(default=False, description="Whether field must be unique")
	default: Optional[Any] = Field(None, description="Default value")
	primary_key: bool = Field(default=False, description="Whether this is a primary key")
	index: bool = Field(default=False, description="Whether to create an index")
	max_length: Optional[int] = Field(None, description="Max length for string fields")


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
    refresh_token_expiration_minutes: int = 10080
    email_verification_expiration_minutes: int = 1440
    password_reset_expiration_minutes: int = 30


class RegistrationSpec(BaseModel):
    mode: Literal["open", "email_verification", "admin_approval"] = "open"


class AuthSpec(BaseModel):
    enabled: bool = False
    jwt: JWTSpec = Field(default_factory=JWTSpec)
    registration: RegistrationSpec = Field(default_factory=RegistrationSpec)


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


class RLSIdentitySource(BaseModel):
    type: Literal["auth_user", "header"]
    header_name: Optional[str] = None

    @model_validator(mode="after")
    def header_name_required_and_valid_for_header_type(self) -> "RLSIdentitySource":
        if self.type == "header":
            if not self.header_name:
                raise ValueError(
                    "rls.identity_source: type 'header' requires 'header_name' to be set "
                    "(e.g. 'X-Tenant-Id')"
                )
            if self.header_name.strip().lower() == "authorization":
                raise ValueError(
                    "rls.identity_source.header_name: must not be 'Authorization' (case-insensitive) "
                    "— this codebase's generated auth already relies on that header for the "
                    "'Bearer <token>' JWT scheme"
                )
        return self


class RLSSpec(BaseModel):
    identity_source: RLSIdentitySource
    bypass_roles: List[str] = Field(default_factory=list)


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
    owner: bool = False
    cascades_ownership: bool = False

    @model_validator(mode="after")
    def owner_and_cascades_ownership_are_valid(self) -> "RelationshipDecl":
        if self.owner and self.cascades_ownership:
            raise ValueError(
                f"relationship '{self.name}': cannot set both 'owner: true' and "
                "'cascades_ownership: true' — a relationship either IS the ownership column "
                "(owner) or passes ownership through from its target (cascades_ownership), never both."
            )
        if (self.owner or self.cascades_ownership) and self.cardinality != Cardinality.MANY_TO_ONE:
            flag = "owner" if self.owner else "cascades_ownership"
            raise ValueError(
                f"relationship '{self.name}': '{flag}: true' is only valid on a many-to-one "
                f"relationship (got cardinality '{self.cardinality.value}') — a row can have "
                "exactly one owner, which one-to-many/one-to-one/many-to-many don't resolve to."
            )
        return self


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
    rls: Optional[RLSSpec] = None

    @model_validator(mode="after")
    def at_most_one_owner_and_one_cascades_ownership_relationship(self) -> "EntitySpec":
        owner_rels = [r.name for r in self.relationships if r.owner]
        cascade_rels = [r.name for r in self.relationships if r.cascades_ownership]
        if len(owner_rels) > 1:
            raise ValueError(
                f"entity '{self.name}': more than one relationship has 'owner: true' "
                f"({', '.join(owner_rels)}) — an entity can have exactly one ownership column."
            )
        if len(cascade_rels) > 1:
            raise ValueError(
                f"entity '{self.name}': more than one relationship has 'cascades_ownership: true' "
                f"({', '.join(cascade_rels)}) — an entity can inherit ownership through exactly "
                "one path."
            )
        return self


class ERDConfig(BaseModel):
    project: ProjectMeta
    database: DatabaseSpec
    auth: AuthSpec = Field(default_factory=AuthSpec)
    rbac: RBACSpec = Field(default_factory=RBACSpec)
    entities: List[EntitySpec] = Field(default_factory=list)
    services: List[ServiceDecl] = Field(default_factory=list)
