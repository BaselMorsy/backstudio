"""Load and validate a YAML ERD file into an ERDConfig."""

from pathlib import Path
from typing import Dict, List, Union

import yaml
from pydantic import ValidationError

from app.erd.field_types import enum_class_name, pascal_case
from app.erd.schema import ERDConfig, EntitySpec, FieldType, JWTSpec, RegistrationSpec

RESERVED_USER_FIELDS = {"id", "email", "password_hash", "roles", "is_active", "created_at", "updated_at"}
MODE_GATED_RESERVED_USER_FIELDS = {
    "email_verification": {"is_verified"},
    "admin_approval": {"is_approved"},
}


class ERDValidationError(Exception):
    """Raised when an ERD file fails to parse or fails semantic validation."""


def load_erd(path: Union[str, Path]) -> ERDConfig:
    path = Path(path)
    if not path.exists():
        raise ERDValidationError(f"ERD file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ERDValidationError(f"Invalid YAML in {path}: {exc}") from exc

    if raw is None:
        raise ERDValidationError(f"ERD file is empty: {path}")
    if not isinstance(raw, dict):
        raise ERDValidationError(f"ERD file must contain a mapping at the top level: {path}")

    try:
        erd = ERDConfig(**raw)
    except ValidationError as exc:
        raise ERDValidationError(f"ERD schema validation failed:\n{exc}") from exc

    _validate_semantics(erd)
    return erd


def _validate_external_auth(erd: ERDConfig) -> None:
    if erd.auth.mode == "external":
        if "jwt" in erd.auth.model_fields_set and erd.auth.jwt != JWTSpec():
            raise ERDValidationError(
                "auth.mode: external cannot be combined with a customized auth.jwt block - "
                "JWT signing is not this service's job when identity is verified externally."
            )
        if "registration" in erd.auth.model_fields_set and erd.auth.registration != RegistrationSpec():
            raise ERDValidationError(
                "auth.mode: external cannot be combined with a customized auth.registration "
                "block - there is no registration flow when identity is verified externally."
            )
        for entity in erd.entities:
            if entity.name == "User":
                raise ERDValidationError(
                    "auth.mode: external does not support a declared 'User' entity - there is "
                    "no builtin User table to merge it into (identity comes entirely from the "
                    "verified token)."
                )


def _validate_jwt_claim_rls(erd: ERDConfig, entity: EntitySpec) -> None:
    source = entity.rls.identity_source
    if source.type == "jwt_claim":
        if not (erd.auth.enabled and erd.auth.mode == "external"):
            raise ERDValidationError(
                f"Entity '{entity.name}': rls.identity_source.type 'jwt_claim' requires "
                "auth.enabled: true and auth.mode: external (there is no verified-claims "
                "source to read from otherwise)."
            )
    elif entity.rls.owner_match_field is not None:
        raise ERDValidationError(
            f"Entity '{entity.name}': rls.owner_match_field is only valid when "
            "rls.identity_source.type: jwt_claim."
        )

    if entity.rls.owner_match_field is not None:
        owner_rel = next((r for r in entity.relationships if r.owner), None)
        owner_entity = next((e for e in erd.entities if e.name == owner_rel.target), None)
        if owner_entity is None:
            return  # a different pre-existing validator reports the unknown-target error
        match_field = next((f for f in owner_entity.fields if f.name == entity.rls.owner_match_field), None)
        if match_field is None:
            raise ERDValidationError(
                f"Entity '{entity.name}': rls.owner_match_field '{entity.rls.owner_match_field}' "
                f"does not name a field on owner entity '{owner_entity.name}'."
            )
        if not match_field.unique:
            raise ERDValidationError(
                f"Entity '{entity.name}': rls.owner_match_field '{entity.rls.owner_match_field}' "
                f"on entity '{owner_entity.name}' must be declared 'unique: true' - a non-unique "
                "match field makes 'the owner row' ambiguous, which is exactly the shape of bug "
                "that turns into a cross-tenant data leak."
            )
        allowed_types = {"string", "uuid", "integer", "bigint"}
        if match_field.type.value not in allowed_types:
            raise ERDValidationError(
                f"Entity '{entity.name}': rls.owner_match_field '{entity.rls.owner_match_field}' "
                f"on entity '{owner_entity.name}' has type '{match_field.type.value}', not one of "
                f"{sorted(allowed_types)} - not a sensible identity-matching value."
            )


def _validate_rls(erd: ERDConfig, known_entities: set) -> None:
    owner_targets: Dict[str, str] = {}  # entity name -> its owner:true relationship's target
    for entity in erd.entities:
        owner_rel = next((r for r in entity.relationships if r.owner), None)
        if owner_rel is None:
            continue
        owner_targets[entity.name] = owner_rel.target

        if entity.rls is None:
            raise ERDValidationError(
                f"Entity '{entity.name}': relationship '{owner_rel.name}' has 'owner: true' but "
                f"the entity declares no 'rls:' block — every 'owner: true' entity must declare "
                "'rls: {identity_source: ...}'."
            )

        source = entity.rls.identity_source
        if source.type == "auth_user":
            if not erd.auth.enabled:
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.identity_source.type 'auth_user' requires "
                    "auth.enabled: true (there is no JWT-authenticated caller to resolve "
                    "ownership from otherwise)."
                )
            if erd.auth.mode == "external":
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.identity_source.type 'auth_user' requires "
                    "auth.mode: builtin — there is no injected User table under "
                    "auth.mode: external to resolve ownership from. Use "
                    "rls.identity_source.type: jwt_claim instead."
                )
            if owner_rel.target != "User":
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.identity_source.type 'auth_user' requires the "
                    f"'owner: true' relationship's target to be 'User' (got '{owner_rel.target}') "
                    "— auth_user resolves ownership from the JWT-authenticated User; a different "
                    "owner entity needs rls.identity_source.type: header instead."
                )

        if entity.rls.read_scope == "any_authenticated" and source.type == "header":
            if not erd.auth.enabled:
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.read_scope 'any_authenticated' on a "
                    "header-identity entity requires auth.enabled: true — the generated "
                    "list/read routes must depend on a real authenticated-user check so that "
                    "'any_authenticated' genuinely means 'the caller presented a valid JWT', "
                    "and there is no auth module generated to depend on otherwise."
                )

        if entity.rls.bypass_roles:
            if not erd.rbac.enabled:
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.bypass_roles requires rbac.enabled: true "
                    "(bypass roles are RBAC roles)."
                )
            unknown = sorted(set(entity.rls.bypass_roles) - set(erd.rbac.roles))
            if unknown:
                raise ERDValidationError(
                    f"Entity '{entity.name}': rls.bypass_roles references unknown role(s): "
                    f"{', '.join(unknown)} — declared roles are: "
                    f"{', '.join(erd.rbac.roles) or 'none declared'}."
                )

        _validate_jwt_claim_rls(erd, entity)

    for entity in erd.entities:
        cascade_rel = next((r for r in entity.relationships if r.cascades_ownership), None)
        if cascade_rel is None:
            continue
        # Walk up the cascades_ownership chain (bounded by len(erd.entities) to avoid an
        # infinite loop on a cycle here too - Task 3's resolver gives the authoritative,
        # precise cycle error; this is a coarser, cheaper pre-check).
        current = cascade_rel.target
        seen = {entity.name}
        steps = 0
        by_name = {e.name: e for e in erd.entities}
        while steps <= len(erd.entities):
            if current in owner_targets:
                break  # reached a root-owned entity - structurally valid
            if current in seen or current not in by_name:
                raise ERDValidationError(
                    f"Entity '{entity.name}': relationship '{cascade_rel.name}' "
                    f"(cascades_ownership: true, target '{cascade_rel.target}') does not lead to "
                    "any entity with 'owner: true' — either the chain doesn't terminate at an "
                    "owned entity, or it cycles back on itself."
                )
            seen.add(current)
            next_entity = by_name[current]
            next_cascade = next((r for r in next_entity.relationships if r.cascades_ownership), None)
            if next_cascade is None:
                raise ERDValidationError(
                    f"Entity '{entity.name}': relationship '{cascade_rel.name}' "
                    f"(cascades_ownership: true, target '{cascade_rel.target}') does not lead to "
                    "any entity with 'owner: true' — either the chain doesn't terminate at an "
                    "owned entity, or it cycles back on itself."
                )
            current = next_cascade.target
            steps += 1
        else:
            raise ERDValidationError(
                f"Entity '{entity.name}': relationship '{cascade_rel.name}' "
                f"(cascades_ownership: true, target '{cascade_rel.target}') does not lead to "
                "any entity with 'owner: true' — either the chain doesn't terminate at an "
                "owned entity, or it cycles back on itself."
            )


_RESERVED_IMPORT_NAMES = {
    "Column", "Integer", "String", "Boolean", "DateTime", "Date", "Float", "Text", "JSON",
    "ForeignKey", "Table", "BigInteger", "Enum", "Numeric", "Uuid", "Decimal", "UUID",
    "BaseModel", "Field", "Optional", "Any", "List", "Base",
}


def _validate_enum_fields(erd: ERDConfig) -> None:
    """Enum fields generate `database/enums.py` classes named <Entity><Field>; those names
    must be unique, must not equal any entity's model class (models.py would silently rebind
    the name), and must not collide with a generated <Entity>Create/Update/Response schema
    class or a name the templates import (e.g. an enum field literally named "create" on
    entity "Survey" would generate "SurveyCreate", silently rebinding the Pydantic schema
    class of the same name and breaking every route that uses it)."""
    model_class_names = {pascal_case(e.name) for e in erd.entities} | {"User"}
    reserved = (
        model_class_names
        | {name + suffix for name in model_class_names for suffix in ("Create", "Update", "Response")}
        | _RESERVED_IMPORT_NAMES
    )
    seen: Dict[str, str] = {}
    for entity in erd.entities:
        for field in entity.fields:
            if field.type != FieldType.ENUM:
                continue
            class_name = enum_class_name(entity.name, field.name)
            owner = f"{entity.name}.{field.name}"
            if class_name in reserved:
                raise ERDValidationError(
                    f"{owner}: the generated enum class '{class_name}' collides with a generated "
                    "class or import name (an entity's model class, its Create/Update/Response "
                    "schema, or a name the templates import) - rename the field or the entity."
                )
            if class_name in seen:
                raise ERDValidationError(
                    f"{owner} and {seen[class_name]} would both generate the enum class "
                    f"'{class_name}' - rename one of the fields."
                )
            seen[class_name] = owner


def _validate_semantics(erd: ERDConfig) -> None:
    if not erd.entities:
        raise ERDValidationError("ERD must declare at least one entity")

    if erd.rbac.enabled and not erd.auth.enabled:
        raise ERDValidationError(
            "rbac.enabled requires auth.enabled: true (RBAC needs a way to identify the current user)"
        )

    if erd.rbac.enabled and "admin" not in erd.rbac.roles:
        raise ERDValidationError(
            "rbac.enabled requires 'admin' to be declared in rbac.roles — the auto-generated "
            "admin user-management endpoints (list/get/set-roles/deactivate/reactivate users) "
            "are gated to that specific role name, exactly like 'User' is a reserved entity "
            f"name. Declared roles: {', '.join(erd.rbac.roles) or 'none'}."
        )

    if erd.auth.registration.mode == "admin_approval" and not erd.rbac.enabled:
        raise ERDValidationError(
            "auth.registration.mode: admin_approval requires rbac.enabled: true — the "
            "'POST /users/{id}/approve' endpoint that approves a pending registration is "
            "gated to the 'admin' role, which requires RBAC to exist."
        )

    entity_names = [e.name for e in erd.entities]
    duplicates = sorted({n for n in entity_names if entity_names.count(n) > 1})
    if duplicates:
        raise ERDValidationError(f"Duplicate entity name(s): {', '.join(duplicates)}")

    if not erd.auth.enabled and "User" in entity_names:
        raise ERDValidationError(
            "Entity 'User' is reserved for the auto-managed auth entity, but auth.enabled is "
            "false — a declared 'User' entity would be silently dropped from generation. "
            "Either rename this entity, or set auth.enabled: true (declared fields on 'User' "
            "are then merged into the auto-injected auth fields)."
        )

    known_entities = set(entity_names) | (
        {"User"} if erd.auth.enabled and erd.auth.mode == "builtin" else set()
    )

    _validate_rls(erd, known_entities)

    for entity in erd.entities:
        field_names = [f.name for f in entity.fields]
        dup_fields = sorted({n for n in field_names if field_names.count(n) > 1})
        if dup_fields:
            raise ERDValidationError(
                f"Entity '{entity.name}': duplicate field name(s): {', '.join(dup_fields)}"
            )

        if entity.name == "User" and erd.auth.enabled:
            reserved = RESERVED_USER_FIELDS | MODE_GATED_RESERVED_USER_FIELDS.get(erd.auth.registration.mode, set())
            collide = sorted(set(field_names) & reserved)
            if collide:
                raise ERDValidationError(
                    f"Entity 'User': field(s) {', '.join(collide)} collide with auto-injected auth "
                    f"fields ({', '.join(sorted(reserved))}) — rename the colliding "
                    "field(s) on your declared 'User' entity."
                )

        for rel in entity.relationships:
            if rel.target == entity.name and rel.cardinality.value == "many-to-many":
                raise ERDValidationError(
                    f"Entity '{entity.name}': relationship '{rel.name}' is a self-referential "
                    "many-to-many — not yet supported by the CLI's code generation (it would "
                    "collide on the association table's column names; modeling a symmetric "
                    "self-relationship needs more than this generator's naming conventions can "
                    "resolve automatically). Self-referential many-to-one, one-to-one, and "
                    "one-to-many relationships are supported."
                )
            if rel.target not in known_entities:
                raise ERDValidationError(
                    f"Entity '{entity.name}': relationship '{rel.name}' target "
                    f"'{rel.target}' not found among declared entities "
                    f"({', '.join(sorted(known_entities)) or 'none declared'}) — check the spelling, "
                    "or declare the target entity in the ERD's 'entities:' list."
                )

        if erd.rbac.enabled and entity.endpoints.rbac is not None:
            overrides = entity.endpoints.rbac.model_dump(exclude_none=True)
            for action, roles in overrides.items():
                unknown = sorted(set(roles) - set(erd.rbac.roles))
                if unknown:
                    raise ERDValidationError(
                        f"Entity '{entity.name}': endpoints.rbac.{action} references "
                        f"unknown role(s): {', '.join(unknown)} — declared roles are: "
                        f"{', '.join(erd.rbac.roles) or 'none declared'} (add missing roles to "
                        "rbac.roles, or fix the typo)."
                    )

    _validate_enum_fields(erd)

    _validate_external_auth(erd)

    _validate_services(erd)

    if erd.rbac.enabled:
        for action, roles in erd.rbac.default_permissions.items():
            unknown = sorted(set(roles) - set(erd.rbac.roles))
            if unknown:
                raise ERDValidationError(
                    f"rbac.default_permissions.{action} references unknown role(s): "
                    f"{', '.join(unknown)} — declared roles are: "
                    f"{', '.join(erd.rbac.roles) or 'none declared'} (add missing roles to "
                    "rbac.roles, or fix the typo)."
                )


def _validate_services(erd: ERDConfig) -> None:
    service_names = [s.name for s in erd.services]
    dup_service_names = sorted({n for n in service_names if service_names.count(n) > 1})
    if dup_service_names:
        raise ERDValidationError(f"Duplicate service name(s): {', '.join(dup_service_names)}")

    if erd.auth.enabled:
        auth_module_name = next((s.name for s in erd.services if s.entities == ["User"]), "auth")
        colliding = [s.name for s in erd.services if s.entities != ["User"] and s.name == auth_module_name]
        if colliding:
            raise ERDValidationError(
                f"Service '{auth_module_name}': collides with the auth service's module name — "
                "rename it, or rename the auth service by declaring a services entry with entities: [User]"
            )

    entity_names = {e.name for e in erd.entities if e.name != "User"}
    assigned: Dict[str, List[str]] = {}
    auth_services: List[str] = []

    for svc in erd.services:
        if "User" in svc.entities:
            if not erd.auth.enabled:
                raise ERDValidationError(
                    f"Service '{svc.name}': references entity 'User', but auth.enabled is false "
                    "(there is no auto-injected User entity to reference)"
                )
            if svc.entities != ["User"]:
                raise ERDValidationError(
                    f"Service '{svc.name}': the auth entity 'User' must be the only entity in its "
                    f"service (found: {', '.join(svc.entities)})"
                )
            if svc.prefix is not None:
                raise ERDValidationError(
                    f"Service '{svc.name}': services[].prefix has no effect on the auth service "
                    "(entities: [User]) - the auth router is always mounted at "
                    "'/<this service's name>'. Rename the service instead, or remove the prefix."
                )
            auth_services.append(svc.name)
            continue

        for ent_name in svc.entities:
            if ent_name not in entity_names:
                raise ERDValidationError(
                    f"Service '{svc.name}': references unknown entity '{ent_name}'"
                )
            assigned.setdefault(ent_name, []).append(svc.name)

    if len(auth_services) > 1:
        raise ERDValidationError(
            f"Entity 'User' is assigned to multiple services: {', '.join(sorted(auth_services))}"
        )

    unassigned = sorted(entity_names - set(assigned.keys()))
    if unassigned:
        raise ERDValidationError(
            f"Entity(ies) not assigned to any service: {', '.join(unassigned)} — every entity "
            "must belong to exactly one service. Add each to a 'services:' entry's 'entities:' "
            "list at the end of the ERD file (e.g. '- {name: <service>, entities: "
            f"[{unassigned[0]}]}}')."
        )

    multiply_assigned = {name: svcs for name, svcs in assigned.items() if len(svcs) > 1}
    if multiply_assigned:
        details = "; ".join(
            f"'{name}' in ({', '.join(svcs)})" for name, svcs in sorted(multiply_assigned.items())
        )
        raise ERDValidationError(
            f"Entity(ies) assigned to multiple services: {details} — each entity must belong to "
            "exactly one service. Remove it from all but one service's 'entities:' list."
        )
