"""Translate a validated ERDConfig into the state dict CodeGenerator.generate_project expects."""

import re
from collections import Counter
from typing import Any, Dict, List

from backend.erd.loader import ERDValidationError
from backend.erd.schema import ALL_ACTIONS, ERDConfig, EntitySpec, RelationshipDecl

AUTH_USER_FIELDS: List[Dict[str, Any]] = [
    {"name": "id", "type": "integer", "primary_key": True, "nullable": False, "default": None},
    {"name": "email", "type": "string", "unique": True, "nullable": False, "max_length": 255, "default": None},
    {"name": "password_hash", "type": "string", "nullable": False, "max_length": 255, "default": None},
    {"name": "roles", "type": "json", "nullable": False, "default": []},
    {"name": "is_active", "type": "boolean", "nullable": False, "default": True},
    {"name": "created_at", "type": "datetime", "nullable": False, "default": None},
    {"name": "updated_at", "type": "datetime", "nullable": False, "default": None},
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


def _build_relationship(
    erd: ERDConfig, entity: EntitySpec, rel: RelationshipDecl, use_name_basis: bool
) -> Dict[str, Any]:
    """Build the relationship dict for one declared relationship.

    `use_name_basis` is True when `entity` declares more than one relationship
    targeting `rel.target` (e.g. Message.sender and Message.recipient both
    targeting Person). In that case the generic target-derived attribute/FK
    names (which don't incorporate `rel.name` at all) would collide across the
    two relationships, silently overwriting one in the generated SQLAlchemy
    class. When ambiguous, `rel.name` becomes the basis for every derived name
    instead, keeping both relationships distinct.
    """
    entity_table = _table_name(erd, entity.name)
    target_table = _table_name(erd, rel.target)
    name_basis = _snake_case(rel.name)

    if rel.cardinality == "one-to-many":
        source_attribute = rel.attribute or (name_basis if use_name_basis else _pluralize(rel.target))
        target_attribute = rel.target_attribute or (name_basis if use_name_basis else _snake_case(entity.name))
    elif rel.cardinality == "many-to-one":
        source_attribute = rel.attribute or (name_basis if use_name_basis else _snake_case(rel.target))
        target_attribute = rel.target_attribute or (
            f"{name_basis}_{_pluralize(entity.name)}" if use_name_basis else _pluralize(entity.name)
        )
    elif rel.cardinality == "one-to-one":
        source_attribute = rel.attribute or (name_basis if use_name_basis else _snake_case(rel.target))
        target_attribute = rel.target_attribute or (
            f"{name_basis}_{_snake_case(entity.name)}" if use_name_basis else _snake_case(entity.name)
        )
    else:  # many-to-many
        source_attribute = rel.attribute or (name_basis if use_name_basis else _pluralize(rel.target))
        target_attribute = rel.target_attribute or (
            f"{name_basis}_{_pluralize(entity.name)}" if use_name_basis else _pluralize(entity.name)
        )

    rel_dict: Dict[str, Any] = {
        "id": rel.name,
        "name": rel.name,
        "cardinality": rel.cardinality.value,
        "source": {"model": entity.name, "attribute": source_attribute, "lazy": rel.lazy.value if rel.lazy else None},
        "target": {"model": rel.target, "attribute": target_attribute},
    }

    if rel.cardinality == "many-to-many":
        default_table_name = (
            f"{_snake_case(entity.name)}_{name_basis}" if use_name_basis
            else f"{_snake_case(entity.name)}_{_snake_case(rel.target)}"
        )
        table_name = rel.association_table or default_table_name
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
        fk_column = rel.foreign_key_column or (f"{name_basis}_id" if use_name_basis else f"{_snake_case(entity.name)}_id")
        fk_references = f"{entity_table}.id"
    else:  # many-to-one or one-to-one: this entity owns the FK column
        fk_model = entity.name
        fk_column = rel.foreign_key_column or (f"{name_basis}_id" if use_name_basis else f"{_snake_case(rel.target)}_id")
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


def _validate_relationship_uniqueness(entity_name: str, rels: List[Dict[str, Any]]) -> None:
    """Raise if two relationships attached to `entity_name` would derive the same
    attribute name or the same FK column name on that entity - better to fail
    loudly at translation time than silently drop/overwrite one in the generated
    SQLAlchemy class.
    """
    seen_attrs: Dict[str, str] = {}
    seen_fks: Dict[str, str] = {}
    for rel_dict in rels:
        attribute = (
            rel_dict["source"]["attribute"] if rel_dict["source"]["model"] == entity_name
            else rel_dict["target"]["attribute"]
        )
        prior = seen_attrs.get(attribute)
        if prior is not None and prior != rel_dict["name"]:
            raise ERDValidationError(
                f"Entity '{entity_name}': relationships '{prior}' and '{rel_dict['name']}' both derive the "
                f"attribute name '{attribute}'. Set an explicit 'attribute'/'target_attribute' on one of them "
                "to disambiguate."
            )
        seen_attrs[attribute] = rel_dict["name"]

        fk = rel_dict.get("foreign_key")
        if fk and fk["model"] == entity_name:
            column = fk["column"]
            prior_fk = seen_fks.get(column)
            if prior_fk is not None and prior_fk != rel_dict["name"]:
                raise ERDValidationError(
                    f"Entity '{entity_name}': relationships '{prior_fk}' and '{rel_dict['name']}' both derive "
                    f"the foreign key column '{column}'. Set an explicit 'foreign_key_column' on one of them "
                    "to disambiguate."
                )
            seen_fks[column] = rel_dict["name"]


def _build_user_entity(erd: ERDConfig) -> Dict[str, Any]:
    declared = next((e for e in erd.entities if e.name == "User"), None)
    fields = [dict(f) for f in AUTH_USER_FIELDS]
    if declared:
        fields.extend(f.model_dump(mode='json') for f in declared.fields)
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


def _resolve_auth_module_name(erd: ERDConfig) -> str:
    for svc in erd.services:
        if svc.entities == ["User"]:
            return _snake_case(svc.name)
    return "auth"


def _resolve_modules(erd: ERDConfig, crud_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_name = {e["name"]: e for e in crud_entities}
    modules: List[Dict[str, Any]] = []
    for svc in erd.services:
        if svc.entities == ["User"]:
            continue  # the auth service is resolved separately via auth_module_name
        modules.append({
            "name": svc.name,
            "snake_name": _snake_case(svc.name),
            "entities": [by_name[name] for name in svc.entities],
        })
    return modules


def translate(erd: ERDConfig) -> Dict[str, Any]:
    entities = [e for e in erd.entities if e.name != "User"]

    data_models: Dict[str, Dict[str, Any]] = {
        entity.name: {
            "name": entity.name,
            "table_name": _table_name(erd, entity.name),
            "fields": [f.model_dump(mode='json') for f in entity.fields],
            "relationships": [],
        }
        for entity in entities
    }

    if erd.auth.enabled:
        data_models["User"] = _build_user_entity(erd)

    relationships: List[Dict[str, Any]] = []
    for entity in entities:
        target_counts = Counter(rel.target for rel in entity.relationships)
        for rel in entity.relationships:
            use_name_basis = target_counts[rel.target] > 1
            rel_dict = _build_relationship(erd, entity, rel, use_name_basis)
            relationships.append(rel_dict)
            if entity.name in data_models:
                data_models[entity.name]["relationships"].append(rel_dict)
            if rel.target in data_models:
                data_models[rel.target]["relationships"].append(rel_dict)

    for model_name, model in data_models.items():
        _validate_relationship_uniqueness(model_name, model["relationships"])

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
            "fields": [f.model_dump(mode='json') for f in entity.fields],
        })

    modules = _resolve_modules(erd, crud_entities)
    auth_module_name = _resolve_auth_module_name(erd)

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
        "database_config": erd.database.model_dump(mode='json'),
        "security_config": security_config,
        "modules": modules,
        "auth_module_name": auth_module_name,
        "auth_enabled": erd.auth.enabled,
        "rbac_enabled": erd.rbac.enabled,
        "rbac_roles": erd.rbac.roles,
    }
