"""Translate a validated ERDConfig into the state dict CodeGenerator.generate_project expects."""

import re
from collections import Counter
from typing import Any, Dict, List

from app.erd.loader import ERDValidationError
from app.erd.schema import ALL_ACTIONS, ERDConfig, EntitySpec, RelationshipDecl

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
    # Must stay identical to `to_snake_case` in app/services/code_generator.py
    # (the Jinja `snake_case` filter) - module_service.py.jinja calls
    # repo.get_<target_snake>_by_id using THIS function's output, so any drift
    # between the two would generate a call to a repo function that doesn't exist.
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
    is_self_referential = entity.name == rel.target

    if rel.cardinality == "one-to-many":
        source_attribute = rel.attribute or (name_basis if use_name_basis else _pluralize(rel.target))
        if is_self_referential:
            # The generic default (name_basis alone, or entity-name-derived) would collide
            # with source_attribute since both live on the same class for a self-referential
            # relationship - suffix with the entity name, mirroring one-to-one's convention,
            # to keep the two sides distinct (e.g. Category.children / Category.children_category).
            target_attribute = rel.target_attribute or f"{name_basis}_{_snake_case(entity.name)}"
        else:
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
        "owner": rel.owner,
        "cascades_ownership": rel.cascades_ownership,
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

    A self-referential relationship appears twice in `rels` (once per `_view`,
    see `translate()`) - both entries share the same `name` but must resolve to
    *different* attributes (they're two distinct relationship() declarations on
    the same class), so the attribute check keys on `(name, view)` rather than
    `name` alone. The FK-column check stays keyed on `name` alone: both views of
    a self-referential relationship legitimately share the same FK column, and
    that's not a collision - only two genuinely different relationships (a real
    name mismatch) claiming the same column is.
    """
    seen_attrs: Dict[str, Any] = {}
    seen_fks: Dict[str, str] = {}
    for rel_dict in rels:
        view = rel_dict.get("_view")
        is_source = (view == "source") if view is not None else (rel_dict["source"]["model"] == entity_name)
        attribute = rel_dict["source"]["attribute"] if is_source else rel_dict["target"]["attribute"]
        claim_key = (rel_dict["name"], view)
        prior = seen_attrs.get(attribute)
        if prior is not None and prior != claim_key:
            raise ERDValidationError(
                f"Entity '{entity_name}': relationships '{prior[0]}' and '{rel_dict['name']}' both derive the "
                f"attribute name '{attribute}'. Set an explicit 'attribute'/'target_attribute' on one of them "
                "to disambiguate."
            )
        seen_attrs[attribute] = claim_key

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


def _owned_relationships_for(entity_name: str, rels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Relationships where `entity_name` owns the FK column - regardless of which
    cardinality keyword declared it (a one-to-many declared from the parent side and
    the equivalent many-to-one declared from the child side both normalize to the
    same foreign_key.model in _build_relationship, so this check covers both).

    A self-referential relationship appears twice in `rels` (once per `_view`) but
    owns exactly one FK column - dedupe back down to a single entry, and make sure
    it's specifically the FK-owning view's attribute that's kept (not just whichever
    of the two happens to be encountered first): many-to-one/one-to-one own the FK
    from the source side, one-to-many from the target side, mirroring
    _build_relationship's fk_model assignment.
    """
    owned: List[Dict[str, Any]] = []
    seen_names: set = set()
    for rel in rels:
        fk = rel.get("foreign_key")
        if not fk or fk["model"] != entity_name:
            continue
        if rel["name"] in seen_names:
            continue
        view = rel.get("_view")
        if view is not None:
            is_fk_owner_view = (view == "source") if rel["cardinality"] != "one-to-many" else (view == "target")
            if not is_fk_owner_view:
                continue
            is_source = view == "source"
        else:
            is_source = rel["source"]["model"] == entity_name
        seen_names.add(rel["name"])
        other_model = rel["target"]["model"] if is_source else rel["source"]["model"]
        owned.append({
            "attribute": rel["source"]["attribute"] if is_source else rel["target"]["attribute"],
            "fk_column": fk["column"],
            "fk_nullable": fk["nullable"],
            "target_model": other_model,
            "target_snake": _snake_case(other_model),
            "owner": rel.get("owner", False),
            "cascades_ownership": rel.get("cascades_ownership", False),
        })
    return owned


def _many_to_many_relationships_for(entity_name: str, rels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """See `_owned_relationships_for` - same `_view`-aware dedup, for the case of a
    (currently rejected at validation time, see loader.py) self-referential
    many-to-many relationship, so this stays correct if that's ever lifted.
    """
    m2m: List[Dict[str, Any]] = []
    seen_names: set = set()
    for rel in rels:
        if rel["cardinality"] != "many-to-many":
            continue
        if rel["name"] in seen_names:
            continue
        seen_names.add(rel["name"])
        view = rel.get("_view")
        is_source = (view == "source") if view is not None else (rel["source"]["model"] == entity_name)
        other_model = rel["target"]["model"] if is_source else rel["source"]["model"]
        m2m.append({
            "attribute": rel["source"]["attribute"] if is_source else rel["target"]["attribute"],
            "target_model": other_model,
            "target_plural_snake": _pluralize(other_model),
        })
    return m2m


def _resolve_rls(erd: ERDConfig, data_models: Dict[str, Dict[str, Any]]) -> None:
    """Resolve every entity's ownership (unowned / root-owned / cascade-owned), attaching
    `rls` (the structure documented in the RLS plan's Global Constraints) to every model in
    `data_models`, and marking exactly the RLS-governing relationship's `is_rls_link: True`
    inside that model's `owned_relationships`. Must run after `owned_relationships` has been
    populated on every model (reads `model["owned_relationships"]`), before `crud_entities`
    is built (which copies `data_models[...]["owned_relationships"]` and needs `rls` too).
    """
    for model in data_models.values():
        model["rls"] = None
        for rel in model["owned_relationships"]:
            rel["is_rls_link"] = False

    entity_by_name = {e.name: e for e in erd.entities}

    def owner_rel_of(model_name: str) -> Any:
        model = data_models.get(model_name)
        if model is None:
            return None
        return next((r for r in model["owned_relationships"] if r["owner"]), None)

    def cascade_rel_of(model_name: str) -> Any:
        model = data_models.get(model_name)
        if model is None:
            return None
        return next((r for r in model["owned_relationships"] if r["cascades_ownership"]), None)

    def pk_column_of(model_name: str) -> str:
        model = data_models[model_name]
        pk_field = next((f for f in model["fields"] if f.get("primary_key")), None)
        return pk_field["name"] if pk_field else "id"

    def resolve(model_name: str, visiting: frozenset) -> Any:
        model = data_models.get(model_name)
        if model is None:
            return None
        if model["rls"] is not None:
            return model["rls"]

        owner_rel = owner_rel_of(model_name)
        if owner_rel is not None:
            entity = entity_by_name[model_name]
            rls = {
                "is_root": True,
                "root_model": model_name,
                "owner_fk_column": owner_rel["fk_column"],
                "join_chain": [],
                "identity_source": entity.rls.identity_source.model_dump(mode="json"),
                "bypass_roles": list(entity.rls.bypass_roles),
            }
            model["rls"] = rls
            owner_rel["is_rls_link"] = True
            return rls

        cascade_rel = cascade_rel_of(model_name)
        if cascade_rel is None:
            return None

        if model_name in visiting:
            raise ERDValidationError(
                f"Entity '{model_name}': its cascades_ownership chain has a cycle - it "
                "eventually leads back to itself instead of terminating at an owner:true entity."
            )

        parent_name = cascade_rel["target_model"]
        parent_rls = resolve(parent_name, visiting | {model_name})
        if parent_rls is None:
            raise ERDValidationError(
                f"Entity '{model_name}': cascades_ownership relationship targets '{parent_name}', "
                "which does not resolve to any owner:true entity."
            )

        hop = {
            "from_model": model_name,
            "from_fk_column": cascade_rel["fk_column"],
            "to_model": parent_name,
            "to_pk_column": pk_column_of(parent_name),
        }
        rls = {
            "is_root": False,
            "root_model": parent_rls["root_model"],
            "owner_fk_column": parent_rls["owner_fk_column"],
            "join_chain": [hop] + parent_rls["join_chain"],
            "identity_source": parent_rls["identity_source"],
            "bypass_roles": parent_rls["bypass_roles"],
        }
        model["rls"] = rls
        cascade_rel["is_rls_link"] = True
        return rls

    for model_name in list(data_models.keys()):
        resolve(model_name, frozenset())


def _build_user_entity(erd: ERDConfig) -> Dict[str, Any]:
    declared = next((e for e in erd.entities if e.name == "User"), None)
    fields = [dict(f) for f in AUTH_USER_FIELDS]
    if erd.auth.registration.mode == "email_verification":
        fields.append({"name": "is_verified", "type": "boolean", "nullable": False, "default": False})
    elif erd.auth.registration.mode == "admin_approval":
        fields.append({"name": "is_approved", "type": "boolean", "nullable": False, "default": False})
    if declared:
        fields.extend(f.model_dump(mode='json') for f in declared.fields)
    return {
        "name": "User",
        "table_name": "users",
        "plural_snake": _pluralize("User"),
        "fields": fields,
        "relationships": [],
        "owned_relationships": [],
        "many_to_many_relationships": [],
    }


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
            "plural_snake": _pluralize(entity.name),
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
            is_self_referential = entity.name == rel.target
            # Self-referential relationships always get name_basis-derived attribute
            # names: the generic defaults (bare model-name-derived, no rel.name
            # involved) collide once both sides land on the same class - see
            # _build_relationship's is_self_referential branch for one-to-many, and
            # the collision this avoids for one-to-one/many-to-many.
            use_name_basis = target_counts[rel.target] > 1 or is_self_referential
            rel_dict = _build_relationship(erd, entity, rel, use_name_basis)
            relationships.append(rel_dict)
            if is_self_referential:
                # Both "sides" of the relationship live on the same entity here, so
                # a single shared dict can't represent both views (source vs target)
                # at once - append two tagged copies instead of the same object
                # twice, so downstream consumers (the uniqueness validator, the
                # owned/m2m derivation, models.py.jinja) can tell them apart.
                if entity.name in data_models:
                    data_models[entity.name]["relationships"].append({**rel_dict, "_view": "source"})
                    data_models[entity.name]["relationships"].append({**rel_dict, "_view": "target"})
            else:
                if entity.name in data_models:
                    data_models[entity.name]["relationships"].append(rel_dict)
                if rel.target in data_models:
                    data_models[rel.target]["relationships"].append(rel_dict)

    for model_name, model in data_models.items():
        _validate_relationship_uniqueness(model_name, model["relationships"])

    for model in data_models.values():
        model["owned_relationships"] = _owned_relationships_for(model["name"], model["relationships"])
        model["many_to_many_relationships"] = _many_to_many_relationships_for(model["name"], model["relationships"])

    _resolve_rls(erd, data_models)

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
            "owned_relationships": data_models[entity.name]["owned_relationships"],
            "many_to_many_relationships": data_models[entity.name]["many_to_many_relationships"],
            "rls": data_models[entity.name]["rls"],
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
            "jwt_refresh_expiration_minutes": erd.auth.jwt.refresh_token_expiration_minutes,
            "jwt_email_verification_expiration_minutes": erd.auth.jwt.email_verification_expiration_minutes,
            "jwt_password_reset_expiration_minutes": erd.auth.jwt.password_reset_expiration_minutes,
        }

    return {
        "name": erd.project.name,
        "description": erd.project.description,
        "version": erd.project.version,
        "framework": "fastapi",
        "checksum": "",
        "data_models": list(data_models.values()),
        "relationships": relationships,
        "middlewares": [],
        "dependencies": [],
        "database_config": erd.database.model_dump(mode='json'),
        "security_config": security_config,
        "modules": modules,
        "auth_module_name": auth_module_name,
        "auth_enabled": erd.auth.enabled,
        "rbac_enabled": erd.rbac.enabled,
        "rbac_roles": erd.rbac.roles,
        "registration_mode": erd.auth.registration.mode,
    }
