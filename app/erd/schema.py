"""Pydantic schema for the YAML ERD configuration consumed by the backstudio CLI."""

import keyword
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.erd.field_types import is_safe_enum_member, to_decimal, to_uuid


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
    BIGINT = "bigint"
    DECIMAL = "decimal"
    ENUM = "enum"


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
    precision: Optional[int] = Field(None, description="Total digits (decimal fields only)")
    scale: Optional[int] = Field(None, description="Digits after the decimal point (decimal fields only)")
    values: Optional[List[str]] = Field(None, description="Allowed values (enum fields only)")
    timezone: Optional[bool] = Field(None, description="Timezone-aware (datetime fields only; unset means true)")
    description: Optional[str] = Field(None, description="Human-readable description (any type)")

    @model_validator(mode="after")
    def type_specific_attributes_are_valid(self) -> "ModelField":
        where = f"field '{self.name}'"
        if self.type == FieldType.DECIMAL:
            if self.precision is None or self.scale is None:
                raise ValueError(f"{where}: type 'decimal' requires both 'precision' and 'scale'")
            if self.precision < 1 or self.scale < 0 or self.scale > self.precision:
                raise ValueError(
                    f"{where}: decimal needs precision >= 1 and 0 <= scale <= precision "
                    f"(got precision={self.precision}, scale={self.scale})"
                )
            if self.primary_key:
                raise ValueError(f"{where}: a decimal field cannot be a primary key")
            if self.default is not None:
                try:
                    to_decimal(self.default)
                except ValueError as exc:
                    raise ValueError(f"{where}: invalid decimal default: {exc}") from exc
        elif self.precision is not None or self.scale is not None:
            raise ValueError(f"{where}: 'precision'/'scale' are only valid on decimal fields")

        if self.type == FieldType.ENUM:
            if not self.values:
                raise ValueError(f"{where}: type 'enum' requires a non-empty 'values' list")
            if len(set(self.values)) != len(self.values):
                raise ValueError(f"{where}: enum 'values' must be unique")
            bad = [v for v in self.values if not is_safe_enum_member(v)]
            if bad:
                raise ValueError(
                    f"{where}: enum value(s) {bad} cannot be used as generated enum members - use "
                    "letters, digits and underscores, starting with a letter, and avoid Python "
                    "keywords and names that shadow str/Enum attributes (e.g. class, None, mro, "
                    "name, value, count). UPPER_SNAKE_CASE is always safe."
                )
            if self.primary_key:
                raise ValueError(f"{where}: an enum field cannot be a primary key")
            if self.default is not None and self.default not in self.values:
                raise ValueError(f"{where}: default {self.default!r} is not one of the enum values")
        elif self.values is not None:
            raise ValueError(f"{where}: 'values' is only valid on enum fields")

        if self.timezone is not None and self.type != FieldType.DATETIME:
            raise ValueError(f"{where}: 'timezone' is only valid on datetime fields")

        if self.type == FieldType.UUID and self.default is not None:
            try:
                to_uuid(self.default)
            except ValueError as exc:
                raise ValueError(f"{where}: invalid uuid default: {exc}") from exc
        return self


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


ASYMMETRIC_JWT_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})
SYMMETRIC_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})


class JWTSpec(BaseModel):
    secret_env_var: str = "JWT_SECRET"
    issuer: Optional[str] = None
    audience: Optional[str] = None
    algorithm: str = "HS256"
    expiration_minutes: int = 30
    refresh_token_expiration_minutes: int = 10080
    email_verification_expiration_minutes: int = 1440
    password_reset_expiration_minutes: int = 30
    private_key_path_env_var: Optional[str] = None
    public_key_path_env_var: Optional[str] = None
    kid: str = "default"
    claims: Dict[str, str] = Field(default_factory=dict)  # access-token claim name -> User field

    @model_validator(mode="after")
    def key_paths_match_algorithm_family(self) -> "JWTSpec":
        if self.algorithm not in ASYMMETRIC_JWT_ALGORITHMS | SYMMETRIC_JWT_ALGORITHMS:
            raise ValueError(
                f"auth.jwt.algorithm: '{self.algorithm}' is not a recognized algorithm - "
                f"use one of {sorted(SYMMETRIC_JWT_ALGORITHMS)} (shared secret) or "
                f"{sorted(ASYMMETRIC_JWT_ALGORITHMS)} (key pair, publishes JWKS)."
            )
        if self.algorithm in ASYMMETRIC_JWT_ALGORITHMS:
            missing = [
                name
                for name, value in (
                    ("private_key_path_env_var", self.private_key_path_env_var),
                    ("public_key_path_env_var", self.public_key_path_env_var),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    f"auth.jwt.algorithm: '{self.algorithm}' is asymmetric and requires "
                    f"auth.jwt.{' and auth.jwt.'.join(missing)} to be set - backstudio reads "
                    "the key pair from the files at those env vars' paths, it never generates "
                    "or stores key material itself."
                )
            if "secret_env_var" in self.model_fields_set:
                raise ValueError(
                    "auth.jwt.secret_env_var only applies to a symmetric algorithm, but "
                    f"auth.jwt.algorithm is '{self.algorithm}' (asymmetric) - remove it, or "
                    "set a symmetric algorithm."
                )
        else:
            set_fields = [
                name
                for name, value in (
                    ("private_key_path_env_var", self.private_key_path_env_var),
                    ("public_key_path_env_var", self.public_key_path_env_var),
                )
                if value is not None
            ]
            if set_fields:
                raise ValueError(
                    f"auth.jwt.{' and auth.jwt.'.join(set_fields)} only apply to an asymmetric "
                    f"algorithm, but auth.jwt.algorithm is '{self.algorithm}' (symmetric) - "
                    "remove them, or set an asymmetric algorithm."
                )
            if "kid" in self.model_fields_set:
                raise ValueError(
                    "auth.jwt.kid only applies to an asymmetric algorithm, but auth.jwt."
                    f"algorithm is '{self.algorithm}' (symmetric) - remove it, or set an "
                    "asymmetric algorithm."
                )
        return self


class RegistrationSpec(BaseModel):
    mode: Literal["open", "email_verification", "admin_approval"] = "open"


class ExternalClaimRef(BaseModel):
    claim: str
    required: bool = False


# Principal members an extra mapping must not shadow (`roles` and `subject` are the built-in keys).
PRINCIPAL_RESERVED_ATTRIBUTES = frozenset({"id", "claims"})


class ExternalAuthClaims(BaseModel):
    """Maps Principal attributes to token claims; `subject` and `roles` are built in, any other key is extra."""

    model_config = ConfigDict(extra="allow")

    subject: str = "sub"
    roles: str = "roles"

    @model_validator(mode="after")
    def extras_are_valid_attribute_mappings(self) -> "ExternalAuthClaims":
        for name, value in (self.model_extra or {}).items():
            if not name.isidentifier() or keyword.iskeyword(name):
                raise ValueError(
                    f"auth.external.claims.{name}: '{name}' cannot be used as a Principal attribute - "
                    "use a valid Python identifier."
                )
            if name in PRINCIPAL_RESERVED_ATTRIBUTES:
                raise ValueError(
                    f"auth.external.claims.{name}: '{name}' is already a Principal member - "
                    f"pick another attribute name (reserved: {sorted(PRINCIPAL_RESERVED_ATTRIBUTES)})."
                )
            if not isinstance(value, (str, dict)):
                raise ValueError(
                    f"auth.external.claims.{name}: expected a claim name or {{claim: <name>, required: <bool>}}."
                )
            if isinstance(value, dict):
                ExternalClaimRef(**value)  # raises with a field-level message if malformed
        return self

    @property
    def extras(self) -> Dict[str, ExternalClaimRef]:
        refs: Dict[str, ExternalClaimRef] = {}
        for name, value in (self.model_extra or {}).items():
            refs[name] = ExternalClaimRef(claim=value) if isinstance(value, str) else ExternalClaimRef(**value)
        return refs


class ExternalAuthSpec(BaseModel):
    verification: Literal["jwks", "shared_secret"] = "jwks"
    jwks_url_env_var: Optional[str] = None
    secret_env_var: Optional[str] = None
    issuer: str
    audience: Optional[str] = None
    algorithms: List[str] = Field(default_factory=lambda: ["RS256"])
    claims: ExternalAuthClaims = Field(default_factory=ExternalAuthClaims)

    @model_validator(mode="after")
    def algorithms_and_fields_match_verification(self) -> "ExternalAuthSpec":
        if not self.algorithms:
            raise ValueError("auth.external.algorithms must not be empty")
        if self.verification == "jwks":
            if self.jwks_url_env_var is None:
                raise ValueError("auth.external.verification: 'jwks' requires auth.external.jwks_url_env_var")
            if self.secret_env_var is not None:
                raise ValueError(
                    "auth.external.secret_env_var only applies to verification: 'shared_secret' - "
                    "remove it, or set verification: shared_secret"
                )
            hmac_algs = {a for a in self.algorithms if a in SYMMETRIC_JWT_ALGORITHMS}
            if hmac_algs:
                raise ValueError(
                    f"auth.external.algorithms: {sorted(hmac_algs)} are HMAC (symmetric) algorithms - "
                    "a JWKS publishes only public (asymmetric) keys, so accepting an HMAC algorithm "
                    "here is the classic alg-confusion vulnerability: a party who can compute an HMAC "
                    "using the public key material as the shared secret could forge tokens. Use an "
                    "asymmetric algorithm (e.g. RS256, ES256)."
                )
        else:
            if self.secret_env_var is None:
                raise ValueError("auth.external.verification: 'shared_secret' requires auth.external.secret_env_var")
            if self.jwks_url_env_var is not None:
                raise ValueError(
                    "auth.external.jwks_url_env_var only applies to verification: 'jwks' - "
                    "remove it, or set verification: jwks"
                )
            non_hmac_algs = [a for a in self.algorithms if a not in SYMMETRIC_JWT_ALGORITHMS]
            if non_hmac_algs:
                raise ValueError(
                    f"auth.external.algorithms: {sorted(non_hmac_algs)} are not HMAC (symmetric) "
                    "algorithms - verification: 'shared_secret' only supports "
                    f"{sorted(SYMMETRIC_JWT_ALGORITHMS)}. Use verification: jwks for an asymmetric "
                    "algorithm."
                )
        return self


class InviteSpec(BaseModel):
    enabled: bool = False
    expiration_minutes: int = 10080


class WebhookSpec(BaseModel):
    url_env_var: Optional[str] = None
    secret_env_var: Optional[str] = None


class AuthSpec(BaseModel):
    enabled: bool = False
    mode: Literal["builtin", "external"] = "builtin"
    jwt: JWTSpec = Field(default_factory=JWTSpec)
    registration: RegistrationSpec = Field(default_factory=RegistrationSpec)
    external: Optional[ExternalAuthSpec] = None
    invite: InviteSpec = Field(default_factory=InviteSpec)
    webhook: WebhookSpec = Field(default_factory=WebhookSpec)

    @model_validator(mode="after")
    def external_block_matches_mode(self) -> "AuthSpec":
        if self.mode == "external" and self.external is None:
            raise ValueError("auth.mode: external requires auth.external to be set")
        if self.mode == "builtin" and self.external is not None:
            raise ValueError("auth.external is only valid when auth.mode: external - remove it, or set mode: external")
        return self


class RBACSpec(BaseModel):
    enabled: bool = False
    roles: List[str] = Field(default_factory=list)
    default_permissions: Dict[str, List[str]] = Field(default_factory=dict)

    @field_validator("default_permissions")
    @classmethod
    def actions_are_known(cls, v: Dict[str, List[str]]) -> Dict[str, List[str]]:
        for action in v:
            if action not in ALL_ACTIONS:
                raise ValueError(f"rbac.default_permissions: unknown action '{action}' (expected one of {ALL_ACTIONS})")
        return v


class RLSIdentitySource(BaseModel):
    type: Literal["auth_user", "header", "jwt_claim"]
    header_name: Optional[str] = None
    claim: Optional[str] = None

    @model_validator(mode="after")
    def header_name_required_and_valid_for_header_type(self) -> "RLSIdentitySource":
        if self.type == "header":
            if not self.header_name:
                raise ValueError(
                    "rls.identity_source: type 'header' requires 'header_name' to be set (e.g. 'X-Tenant-Id')"
                )
            if self.header_name.strip().lower() == "authorization":
                raise ValueError(
                    "rls.identity_source.header_name: must not be 'Authorization' (case-insensitive) "
                    "— this codebase's generated auth already relies on that header for the "
                    "'Bearer <token>' JWT scheme"
                )
        elif self.header_name is not None:
            raise ValueError("rls.identity_source.header_name is only valid when type: header")

        if self.type == "jwt_claim":
            if not self.claim:
                raise ValueError("rls.identity_source: type 'jwt_claim' requires 'claim' to be set")
        elif self.claim is not None:
            raise ValueError("rls.identity_source.claim is only valid when type: jwt_claim")
        return self


class RLSSpec(BaseModel):
    identity_source: RLSIdentitySource
    bypass_roles: List[str] = Field(default_factory=list)
    read_scope: Literal["owner", "any_authenticated"] = "owner"
    owner_match_field: Optional[str] = None


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
    prefix: Optional[str] = None

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

    @field_validator("prefix")
    @classmethod
    def prefix_is_valid_path_segment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v == "":
            raise ValueError(
                "services: prefix, if set, must not be an empty string - omit the field "
                "entirely (or leave it unset) rather than setting an empty prefix"
            )
        if not v.startswith("/"):
            raise ValueError(f"services: prefix '{v}' must start with '/' (e.g. '/catalog')")
        if v.endswith("/"):
            raise ValueError(
                f"services: prefix '{v}' must not end with '/' (e.g. '/catalog', not '/catalog/') "
                "- a trailing slash would produce a double-slash when combined with an entity's "
                "own route path"
            )
        for ch, label in (('"', "a double quote"), ("'", "a single quote"), ("\\", "a backslash")):
            if ch in v:
                raise ValueError(
                    f"services: prefix {v!r} must not contain {label} - the prefix is embedded "
                    "verbatim into the generated route decorators' path strings, and these "
                    "characters have no legitimate meaning in a URL path segment"
                )
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in v):
            raise ValueError(f"services: prefix {v!r} must not contain control characters")
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
    description: Optional[str] = None

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
