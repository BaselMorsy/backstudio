import pytest

from backend.erd.loader import ERDValidationError, load_erd

FIXTURES = "backend/tests/fixtures/erd"


def test_loads_minimal_valid_erd():
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    assert erd.project.name == "Demo"
    assert len(erd.entities) == 1


def test_loads_full_valid_erd():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    assert erd.auth.enabled is True
    assert erd.rbac.enabled is True
    assert len(erd.entities) == 2


def test_missing_file_raises():
    with pytest.raises(ERDValidationError, match="not found"):
        load_erd(f"{FIXTURES}/does_not_exist.yml")


def test_duplicate_entity_names_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
"""
    )
    with pytest.raises(ERDValidationError, match="Duplicate entity name"):
        load_erd(bad)


def test_unknown_relationship_target_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Product
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: category, cardinality: many-to-one, target: Category}
"""
    )
    with pytest.raises(ERDValidationError, match="not found among declared entities"):
        load_erd(bad)


def test_self_referential_many_to_many_rejected(tmp_path):
    """A self-referential many-to-many would collide on the association table's
    left/right FK column names (both derive to the same "<entity>_id" with no
    disambiguation) and needs primaryjoin/secondaryjoin to model correctly - reject
    it at validation time rather than emitting a broken association table. Other
    self-referential cardinalities (many-to-one, one-to-one, one-to-many) ARE
    supported - see test_erd_translate.py's self-referential tests.
    """
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Person
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: friends, cardinality: many-to-many, target: Person}
services:
  - {name: social, entities: [Person]}
"""
    )
    with pytest.raises(ERDValidationError, match="self-referential many-to-many"):
        load_erd(bad)


def test_self_referential_many_to_one_accepted(tmp_path):
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Employee
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: manager, cardinality: many-to-one, target: Employee}
services:
  - {name: hr, entities: [Employee]}
"""
    )
    erd = load_erd(ok)
    assert erd.entities[0].relationships[0].target == "Employee"


def test_self_referential_one_to_one_accepted(tmp_path):
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Employee
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: buddy, cardinality: one-to-one, target: Employee}
services:
  - {name: hr, entities: [Employee]}
"""
    )
    load_erd(ok)  # must not raise


def test_self_referential_one_to_many_accepted(tmp_path):
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Category
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: children, cardinality: one-to-many, target: Category}
services:
  - {name: catalog, entities: [Category]}
"""
    )
    load_erd(ok)  # must not raise


def test_rbac_without_auth_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
rbac: {enabled: true, roles: [admin]}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
"""
    )
    with pytest.raises(ERDValidationError, match="rbac.enabled requires auth.enabled"):
        load_erd(bad)


def test_unknown_role_reference_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
rbac: {enabled: true, roles: [admin]}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
    endpoints:
      rbac: {delete: [superadmin]}
"""
    )
    with pytest.raises(ERDValidationError, match="unknown role"):
        load_erd(bad)


def test_invalid_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("project: [unterminated")
    with pytest.raises(ERDValidationError, match="Invalid YAML"):
        load_erd(bad)


def test_empty_entities_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities: []
"""
    )
    with pytest.raises(ERDValidationError, match="at least one entity"):
        load_erd(bad)


def test_missing_entities_key_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
"""
    )
    with pytest.raises(ERDValidationError, match="at least one entity"):
        load_erd(bad)


def test_unassigned_entity_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services: []
"""
    )
    with pytest.raises(ERDValidationError, match="not assigned to any service"):
        load_erd(bad)


def test_entity_assigned_to_two_services_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: a, entities: [Widget]}
  - {name: b, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="assigned to multiple services"):
        load_erd(bad)


def test_service_referencing_unknown_entity_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: widgets, entities: [Widget, Gadget]}
"""
    )
    with pytest.raises(ERDValidationError, match="references unknown entity 'Gadget'"):
        load_erd(bad)


def test_duplicate_service_names_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
  - {name: Gadget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: dup, entities: [Widget]}
  - {name: dup, entities: [Gadget]}
"""
    )
    with pytest.raises(ERDValidationError, match="Duplicate service name"):
        load_erd(bad)


def test_user_service_with_extra_entities_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: widgets, entities: [Widget]}
  - {name: identity, entities: [User, Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="must be the only entity"):
        load_erd(bad)


def test_user_service_without_auth_enabled_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: widgets, entities: [Widget]}
  - {name: identity, entities: [User]}
"""
    )
    with pytest.raises(ERDValidationError, match="auth.enabled is false"):
        load_erd(bad)


def test_service_named_auth_collides_with_default_auth_module_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: auth, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="collides with the auth service's module name"):
        load_erd(bad)


def test_user_service_renames_auth_module_without_error():
    # valid_full.yml (updated in this task) does not rename auth; this constructs
    # an inline-equivalent valid case directly to confirm the User-only exception works.
    import tempfile
    from pathlib import Path

    content = """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - {name: Widget, fields: [{name: id, type: integer, primary_key: true}]}
services:
  - {name: widgets, entities: [Widget]}
  - {name: identity, entities: [User]}
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ok.yml"
        path.write_text(content)
        erd = load_erd(path)  # must not raise
        assert erd.services[1].name == "identity"


def test_rls_bypass_roles_requires_rbac_enabled(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: user, cardinality: many-to-one, target: User, owner: true}
    rls:
      bypass_roles: [admin]
      identity_source: {type: auth_user}
services:
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="bypass_roles"):
        load_erd(bad)


def test_rls_bypass_roles_unknown_role_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
rbac: {enabled: true, roles: [customer]}
entities:
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: user, cardinality: many-to-one, target: User, owner: true}
    rls:
      bypass_roles: [admin]
      identity_source: {type: auth_user}
services:
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="unknown role"):
        load_erd(bad)


def test_rls_auth_user_identity_source_requires_auth_enabled(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Tenant
    fields: [{name: id, type: integer, primary_key: true}]
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: tenant, cardinality: many-to-one, target: Tenant, owner: true}
    rls:
      identity_source: {type: auth_user}
services:
  - {name: tenants, entities: [Tenant]}
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="auth\\.enabled"):
        load_erd(bad)


def test_rls_auth_user_identity_source_requires_target_user(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - name: Tenant
    fields: [{name: id, type: integer, primary_key: true}]
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: tenant, cardinality: many-to-one, target: Tenant, owner: true}
    rls:
      identity_source: {type: auth_user}
services:
  - {name: main, entities: [User]}
  - {name: tenants, entities: [Tenant]}
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="target"):
        load_erd(bad)


def test_rls_header_identity_source_does_not_require_auth(tmp_path):
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Tenant
    fields: [{name: id, type: integer, primary_key: true}]
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: tenant, cardinality: many-to-one, target: Tenant, owner: true}
    rls:
      identity_source: {type: header, header_name: X-Tenant-Id}
services:
  - {name: tenants, entities: [Tenant]}
  - {name: orders, entities: [Order]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert erd.entities[1].rls.identity_source.type == "header"


def test_owner_true_entity_missing_rls_block_rejected(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: user, cardinality: many-to-one, target: User, owner: true}
services:
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="rls"):
        load_erd(bad)


def test_cascades_ownership_target_not_owned_rejected(tmp_path):
    """OrderItem cascades_ownership through 'order', but Order carries no owner: true
    anywhere and nothing further up the graph does either - structurally impossible to
    resolve, caught here without needing the full walk Task 3 does.
    """
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
entities:
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
  - name: OrderItem
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: order, cardinality: many-to-one, target: Order, cascades_ownership: true}
services:
  - {name: orders, entities: [Order]}
  - {name: order_items, entities: [OrderItem]}
"""
    )
    with pytest.raises(ERDValidationError, match="does not lead to"):
        load_erd(bad)
