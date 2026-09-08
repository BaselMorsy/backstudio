"""Load and validate a YAML ERD file into an ERDConfig."""

from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError

from backend.erd.schema import ERDConfig

RESERVED_USER_FIELDS = {"id", "email", "password_hash", "roles", "is_active", "created_at", "updated_at"}


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


def _validate_semantics(erd: ERDConfig) -> None:
    if erd.rbac.enabled and not erd.auth.enabled:
        raise ERDValidationError(
            "rbac.enabled requires auth.enabled: true (RBAC needs a way to identify the current user)"
        )

    entity_names = [e.name for e in erd.entities]
    duplicates = sorted({n for n in entity_names if entity_names.count(n) > 1})
    if duplicates:
        raise ERDValidationError(f"Duplicate entity name(s): {', '.join(duplicates)}")

    known_entities = set(entity_names) | ({"User"} if erd.auth.enabled else set())

    for entity in erd.entities:
        field_names = [f.name for f in entity.fields]
        dup_fields = sorted({n for n in field_names if field_names.count(n) > 1})
        if dup_fields:
            raise ERDValidationError(
                f"Entity '{entity.name}': duplicate field name(s): {', '.join(dup_fields)}"
            )

        if entity.name == "User" and erd.auth.enabled:
            collide = sorted(set(field_names) & RESERVED_USER_FIELDS)
            if collide:
                raise ERDValidationError(
                    f"Entity 'User': field(s) {', '.join(collide)} collide with auto-injected auth fields"
                )

        for rel in entity.relationships:
            if rel.target not in known_entities:
                raise ERDValidationError(
                    f"Entity '{entity.name}': relationship '{rel.name}' target "
                    f"'{rel.target}' not found among declared entities"
                )

        if erd.rbac.enabled and entity.endpoints.rbac is not None:
            overrides = entity.endpoints.rbac.model_dump(exclude_none=True)
            for action, roles in overrides.items():
                unknown = sorted(set(roles) - set(erd.rbac.roles))
                if unknown:
                    raise ERDValidationError(
                        f"Entity '{entity.name}': endpoints.rbac.{action} references "
                        f"unknown role(s): {', '.join(unknown)}"
                    )

    if erd.rbac.enabled:
        for action, roles in erd.rbac.default_permissions.items():
            unknown = sorted(set(roles) - set(erd.rbac.roles))
            if unknown:
                raise ERDValidationError(
                    f"rbac.default_permissions.{action} references unknown role(s): {', '.join(unknown)}"
                )
