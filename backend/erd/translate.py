"""Translate a validated ERDConfig into the state dict CodeGenerator.generate_project expects."""

import re
from typing import Any, Dict, List

from backend.erd.schema import ALL_ACTIONS, ERDConfig, EntitySpec, RelationshipDecl

AUTH_USER_FIELDS: List[Dict[str, Any]] = [
    {"name": "id", "type": "integer", "primary_key": True, "nullable": False},
    {"name": "email", "type": "string", "unique": True, "nullable": False, "max_length": 255},
    {"name": "password_hash", "type": "string", "nullable": False, "max_length": 255},
    {"name": "roles", "type": "json", "nullable": False, "default": []},
    {"name": "is_active", "type": "boolean", "nullable": False, "default": True},
    {"name": "created_at", "type": "datetime", "nullable": False},
    {"name": "updated_at", "type": "datetime", "nullable": False},
]


def _snake_case(text: str) -> str:
    text = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text).lower()


def _pluralize(word: str) -> str:
    snake = _snake_case(word)
    if snake.endswith("y") and snake[-2:-1] not in "aeiou":
        return snake[:-1] + "ies"
    if snake.endswith(("s", "x", "z", "ch", "sh")):
        return snake + "es"
    return snake + "s"


def _table_name(erd: ERDConfig, entity_name: str) -> str:
    entity = next((e for e in erd.entities if e.name == entity_name), None)
    if entity and entity.table_name:
        return entity.table_name
    return _pluralize(entity_name)


def _build_relationship(erd: ERDConfig, entity: EntitySpec, rel: RelationshipDecl) -> Dict[str, Any]:
    entity_table = _table_name(erd, entity.name)
    target_table = _table_name(erd, rel.target)

    if rel.cardinality == "one-to-many":
        source_attribute = rel.attribute or _pluralize(rel.target)
        target_attribute = rel.target_attribute or _snake_case(entity.name)
    elif rel.cardinality == "many-to-one":
        source_attribute = rel.attribute or _snake_case(rel.target)
        target_attribute = rel.target_attribute or _pluralize(entity.name)
    elif rel.cardinality == "one-to-one":
        source_attribute = rel.attribute or _snake_case(rel.target)
        target_attribute = rel.target_attribute or _snake_case(entity.name)
    else:  # many-to-many
        source_attribute = rel.attribute or _pluralize(rel.target)
        target_attribute = rel.target_attribute or _pluralize(entity.name)

    rel_dict: Dict[str, Any] = {
        "id": rel.name,
        "name": rel.name,
        "cardinality": rel.cardinality,
        "source": {"model": entity.name, "attribute": source_attribute, "lazy": rel.lazy},
        "target": {"model": rel.target, "attribute": target_attribute},
    }

    if rel.cardinality == "many-to-many":
        table_name = rel.association_table or f"{_snake_case(entity.name)}_{_snake_case(rel.target)}"
        rel_dict["association_table"] = {
            "table_name": table_name,
            "left_foreign_key": {
                "model": entity.name,
                "column": f"{_snake_case(entity.name)}_id",
                "references": f"{entity_table}.id",
            },
            "right_foreign_key": {
                "model": rel.target,
                "column": f"{_snake_case(rel.target)}_id",
                "references": f"{target_table}.id",
            },
        }
        return rel_dict

    if rel.cardinality == "one-to-many":
        fk_model = rel.target
        fk_column = rel.foreign_key_column or f"{_snake_case(entity.name)}_id"
        fk_references = f"{entity_table}.id"
    else:  # many-to-one or one-to-one: this entity owns the FK column
        fk_model = entity.name
        fk_column = rel.foreign_key_column or f"{_snake_case(rel.target)}_id"
        fk_references = f"{target_table}.id"

    rel_dict["foreign_key"] = {
        "model": fk_model,
        "column": fk_column,
        "references": fk_references,
        "nullable": rel.nullable,
        "unique": rel.unique or rel.cardinality == "one-to-one",
        "ondelete": rel.ondelete,
    }
    if rel.cascade:
        rel_dict["behavior"] = {"cascade": rel.cascade}
    return rel_dict


def _build_user_entity(erd: ERDConfig) -> Dict[str, Any]:
    declared = next((e for e in erd.entities if e.name == "User"), None)
    fields = [dict(f) for f in AUTH_USER_FIELDS]
    if declared:
        fields.extend(f.model_dump() for f in declared.fields)
    return {"name": "User", "table_name": "users", "fields": fields, "relationships": []}


def _resolve_rbac(erd: ERDConfig, entity: EntitySpec) -> Dict[str, List[str]]:
    resolved: Dict[str, List[str]] = {}
    overrides = entity.endpoints.rbac.model_dump(exclude_none=True) if entity.endpoints.rbac else {}
    for action in ALL_ACTIONS:
        if action in overrides:
            resolved[action] = overrides[action]
        elif action in erd.rbac.default_permissions:
            resolved[action] = erd.rbac.default_permissions[action]
        elif erd.rbac.enabled:
            resolved[action] = list(erd.rbac.roles)
        else:
            resolved[action] = []
    return resolved


def translate(erd: ERDConfig) -> Dict[str, Any]:
    entities = [e for e in erd.entities if e.name != "User"]

    data_models: Dict[str, Dict[str, Any]] = {
        entity.name: {
            "name": entity.name,
            "table_name": _table_name(erd, entity.name),
            "fields": [f.model_dump() for f in entity.fields],
            "relationships": [],
        }
        for entity in entities
    }

    if erd.auth.enabled:
        data_models["User"] = _build_user_entity(erd)

    relationships: List[Dict[str, Any]] = []
    for entity in entities:
        for rel in entity.relationships:
            rel_dict = _build_relationship(erd, entity, rel)
            relationships.append(rel_dict)
            if entity.name in data_models:
                data_models[entity.name]["relationships"].append(rel_dict)
            if rel.target in data_models:
                data_models[rel.target]["relationships"].append(rel_dict)

    crud_entities: List[Dict[str, Any]] = []
    for entity in entities:
        plural_snake = _pluralize(entity.name)
        crud_entities.append({
            "name": entity.name,
            "snake_name": _snake_case(entity.name),
            "plural_snake": plural_snake,
            "base_path": entity.endpoints.base_path or f"/{plural_snake}",
            "tags": entity.endpoints.tags or [plural_snake],
            "enabled_actions": entity.endpoints.enabled,
            "rbac": _resolve_rbac(erd, entity),
            "fields": [f.model_dump() for f in entity.fields],
        })

    security_config = None
    if erd.auth.enabled:
        security_config = {
            "auth_strategy": "jwt",
            "jwt_secret_env_var": erd.auth.jwt.secret_env_var,
            "jwt_algorithm": erd.auth.jwt.algorithm,
            "jwt_expiration_minutes": erd.auth.jwt.expiration_minutes,
        }

    return {
        "name": erd.project.name,
        "description": erd.project.description,
        "version": erd.project.version,
        "framework": "fastapi",
        "checksum": "",
        "data_models": list(data_models.values()),
        "relationships": relationships,
        "services": [],
        "middlewares": [],
        "dependencies": [],
        "database_config": erd.database.model_dump(),
        "security_config": security_config,
        "crud_entities": crud_entities,
        "auth_enabled": erd.auth.enabled,
        "rbac_enabled": erd.rbac.enabled,
        "rbac_roles": erd.rbac.roles,
    }
