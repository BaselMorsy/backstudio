import pytest

from app.erd.loader import ERDValidationError, load_erd

FIXTURES = "app/tests/fixtures/erd"


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
rbac: {enabled: true, roles: [admin, customer]}
entities:
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: user, cardinality: many-to-one, target: User, owner: true}
    rls:
      bypass_roles: [superadmin]
      identity_source: {type: auth_user}
services:
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="unknown role"):
        load_erd(bad)


def test_rls_bypass_roles_on_header_identity_source_rejected(tmp_path):
    """bypass_roles is only ever read from the *authenticated caller's* roles, and a
    header-sourced entity's owner_id computation never touches role information at all -
    so this combination cannot do anything. Silently-inert configuration in an
    access-control feature is a footgun (the author believes a bypass is active when
    nothing is), so it's rejected at load time rather than ignored.
    """
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
rbac: {enabled: true, roles: [admin]}
entities:
  - name: Tenant
    fields: [{name: id, type: integer, primary_key: true}]
  - name: Order
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: tenant, cardinality: many-to-one, target: Tenant, owner: true}
    rls:
      bypass_roles: [admin]
      identity_source: {type: header, header_name: X-Tenant-Id}
services:
  - {name: tenants, entities: [Tenant]}
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="bypass_roles has no effect"):
        load_erd(bad)


def test_rbac_gated_header_sourced_entity_without_bypass_roles_still_loads():
    """The new bypass_roles+header rejection must not catch the legitimate
    RBAC-gated + header-RLS combination: rls_header_owned_with_rbac.yml gates every
    action on the 'admin' role but never sets rls.bypass_roles, so it must keep loading.
    """
    erd = load_erd(f"{FIXTURES}/rls_header_owned_with_rbac.yml")
    order = next(e for e in erd.entities if e.name == "Order")
    assert order.rls.identity_source.type == "header"
    assert order.rls.bypass_roles == []
    assert erd.rbac.enabled is True
    assert erd.rbac.default_permissions["create"] == ["admin"]


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


def test_cascades_ownership_chain_single_hop_success(tmp_path):
    """OrderItem cascades_ownership through 'order' to Order, which has owner: true
    targeting User (with auth enabled and RLS declared). The chain is structurally valid
    and must not raise.
    """
    ok = tmp_path / "ok.yml"
    ok.write_text(
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
      identity_source: {type: auth_user}
  - name: OrderItem
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: order, cardinality: many-to-one, target: Order, cascades_ownership: true}
services:
  - {name: orders, entities: [Order]}
  - {name: order_items, entities: [OrderItem]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert erd.entities[0].name == "Order"
    assert erd.entities[1].name == "OrderItem"


def test_cascades_ownership_chain_two_hop_success(tmp_path):
    """OrderLineDiscount cascades_ownership -> OrderItem, which cascades_ownership -> Order,
    which has owner: true targeting User. The 2-hop chain is structurally valid and must not raise.
    """
    ok = tmp_path / "ok.yml"
    ok.write_text(
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
      identity_source: {type: auth_user}
  - name: OrderItem
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: order, cardinality: many-to-one, target: Order, cascades_ownership: true}
  - name: OrderLineDiscount
    fields: [{name: id, type: integer, primary_key: true}]
    relationships:
      - {name: order_item, cardinality: many-to-one, target: OrderItem, cascades_ownership: true}
services:
  - {name: orders, entities: [Order]}
  - {name: order_items, entities: [OrderItem]}
  - {name: discounts, entities: [OrderLineDiscount]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert len(erd.entities) == 3
    assert erd.entities[2].name == "OrderLineDiscount"


def test_rbac_enabled_requires_admin_role(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
rbac: {enabled: true, roles: [customer]}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="admin"):
        load_erd(bad)


def test_rbac_enabled_with_admin_role_loads_fine(tmp_path):
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
rbac: {enabled: true, roles: [admin, customer]}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert "admin" in erd.rbac.roles


def test_admin_approval_mode_requires_rbac_enabled(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth:
  enabled: true
  registration: {mode: admin_approval}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="admin_approval"):
        load_erd(bad)


def test_admin_approval_mode_with_rbac_and_admin_role_loads_fine(tmp_path):
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth:
  enabled: true
  registration: {mode: admin_approval}
rbac: {enabled: true, roles: [admin]}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert erd.auth.registration.mode == "admin_approval"


def test_email_verification_mode_needs_no_rbac(tmp_path):
    """email_verification mode has no admin-only endpoint, so it must NOT
    require rbac.enabled - only admin_approval does (it needs the admin-gated
    approve endpoint).
    """
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth:
  enabled: true
  registration: {mode: email_verification}
entities:
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    erd = load_erd(ok)  # must not raise
    assert erd.auth.registration.mode == "email_verification"


def test_declared_user_entity_can_have_is_verified_field_when_mode_is_not_email_verification(tmp_path):
    """RESERVED_USER_FIELDS must be mode-aware: is_verified only collides
    with the auto-injected field when email_verification mode is active.
    """
    ok = tmp_path / "ok.yml"
    ok.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth: {enabled: true}
entities:
  - name: User
    fields:
      - {name: is_verified, type: boolean, default: false}
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    erd = load_erd(ok)  # must not raise - mode is "open", is_verified is not reserved
    assert erd.auth.registration.mode == "open"


def test_declared_user_entity_is_verified_field_collides_under_email_verification_mode(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
project: {name: Demo}
database: {type: sqlite, database_name: d.db}
auth:
  enabled: true
  registration: {mode: email_verification}
entities:
  - name: User
    fields:
      - {name: is_verified, type: boolean, default: false}
  - name: Widget
    fields: [{name: id, type: integer, primary_key: true}]
services:
  - {name: widgets, entities: [Widget]}
"""
    )
    with pytest.raises(ERDValidationError, match="is_verified"):
        load_erd(bad)
