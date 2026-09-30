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


def test_user_service_with_prefix_rejected(tmp_path):
    """services[].prefix has no effect on the auth service: translate()'s
    crud_entities loop skips 'User' entirely (the auth router is always mounted
    at '/<auth service name>' by server.py.jinja), so a prefix set there is
    accepted-but-silently-inert with no error and no effect. Reject it outright
    instead.
    """
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
  - {name: identity, entities: [User], prefix: /api/v1}
"""
    )
    with pytest.raises(ERDValidationError, match="has no effect on the auth service"):
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


def test_rls_bypass_roles_on_header_identity_source_now_loads(tmp_path):
    """bypass_roles + identity_source.type: header used to be hard-rejected (a caller
    whose role membership intersects bypass_roles had no way to be resolved, since the
    header identity source never read role information). Task 3 gives this combination
    real semantics: a bypass-role caller's list/read/update/delete routes skip the
    header-based owner filter entirely (create still requires the header - see
    module_routes.py.jinja and the runtime round-trip tests in
    test_generated_project_runtime.py). So this ERD must load cleanly now, and the
    other two bypass_roles validation rules (rbac.enabled, unknown roles) still apply
    unconditionally regardless of identity_source.type.
    """
    ok = tmp_path / "ok.yml"
    ok.write_text(
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
    erd = load_erd(ok)
    order = next(e for e in erd.entities if e.name == "Order")
    assert order.rls.identity_source.type == "header"
    assert order.rls.bypass_roles == ["admin"]


def test_rls_bypass_roles_on_header_identity_source_still_requires_rbac_enabled(tmp_path):
    """The rbac.enabled: true rule for bypass_roles was never nested inside the removed
    source.type == 'header' check, so it must still apply to header-identity entities.
    """
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
      bypass_roles: [admin]
      identity_source: {type: header, header_name: X-Tenant-Id}
services:
  - {name: tenants, entities: [Tenant]}
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="rbac\\.enabled"):
        load_erd(bad)


def test_rls_bypass_roles_on_header_identity_source_still_rejects_unknown_role(tmp_path):
    """The unknown-role rule for bypass_roles was never nested inside the removed
    source.type == 'header' check either, so it must still apply to header-identity
    entities too.
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
      bypass_roles: [superadmin]
      identity_source: {type: header, header_name: X-Tenant-Id}
services:
  - {name: tenants, entities: [Tenant]}
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="unknown role"):
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


def test_rls_read_scope_any_authenticated_on_header_identity_requires_auth_enabled(tmp_path):
    """read_scope: any_authenticated on a header-identity entity's list/read routes must
    depend on a real authenticated-user check (see module_routes.py.jinja) - but that
    dependency only exists to import when auth.enabled: true generates the auth module at
    all. Without this guard, an ERD could declare a header-identity entity with
    read_scope: any_authenticated and auth.enabled left false (header identity itself does
    not require auth.enabled), which would generate routes referencing a nonexistent
    _auth_service. Rejected at load time instead.
    """
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
      identity_source: {type: header, header_name: X-Tenant-Id}
      read_scope: any_authenticated
services:
  - {name: tenants, entities: [Tenant]}
  - {name: orders, entities: [Order]}
"""
    )
    with pytest.raises(ERDValidationError, match="any_authenticated.*requires auth\\.enabled"):
        load_erd(bad)


def test_rls_read_scope_any_authenticated_on_header_identity_with_auth_enabled_loads(tmp_path):
    """The read_scope: any_authenticated + header-identity + auth.enabled: true combination
    (the fixture this task's runtime test uses) must load cleanly - the guard above only
    rejects the unsafe auth.enabled: false case.
    """
    ok = tmp_path / "ok.yml"
    ok.write_text(
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
      identity_source: {type: header, header_name: X-Tenant-Id}
      read_scope: any_authenticated
services:
  - {name: tenants, entities: [Tenant]}
  - {name: orders, entities: [Order]}
"""
    )
    erd = load_erd(ok)
    order = next(e for e in erd.entities if e.name == "Order")
    assert order.rls.read_scope == "any_authenticated"


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


def _enum_erd(tmp_path, entities, names):
    import yaml

    path = tmp_path / "enum.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "project": {"name": "Demo"},
                "database": {"type": "sqlite", "database_name": "d.db"},
                "entities": entities,
                "services": [{"name": "things", "entities": names}],
            }
        )
    )
    return path


def _entity(name, *fields):
    return {"name": name, "fields": [{"name": "id", "type": "integer", "primary_key": True}, *fields]}


def _enum_field(name, values):
    return {"name": name, "type": "enum", "values": values}


def test_enum_class_colliding_with_an_entity_model_class_rejected(tmp_path):
    path = _enum_erd(
        tmp_path,
        [_entity("Widget", _enum_field("status", ["A", "B"])), _entity("WidgetStatus")],
        ["Widget", "WidgetStatus"],
    )
    with pytest.raises(ERDValidationError, match="WidgetStatus"):
        load_erd(path)


def test_two_enum_fields_generating_the_same_class_rejected(tmp_path):
    path = _enum_erd(
        tmp_path,
        [_entity("Order", _enum_field("item_status", ["A"])), _entity("OrderItem", _enum_field("status", ["B"]))],
        ["Order", "OrderItem"],
    )
    with pytest.raises(ERDValidationError, match="OrderItemStatus"):
        load_erd(path)


def test_distinct_enum_classes_load(tmp_path):
    path = _enum_erd(
        tmp_path,
        [_entity("Widget", _enum_field("status", ["A", "B"]), _enum_field("kind", ["X", "Y"]))],
        ["Widget"],
    )
    assert len(load_erd(path).entities[0].fields) == 3


def test_enum_class_colliding_with_a_generated_create_schema_rejected(tmp_path):
    """Final review F3: an enum field named 'create' on entity 'Survey' would generate the
    class 'SurveyCreate', silently rebinding the Pydantic Create schema of the same name."""
    path = _enum_erd(
        tmp_path,
        [_entity("Survey", _enum_field("create", ["A", "B"]))],
        ["Survey"],
    )
    with pytest.raises(ERDValidationError, match="SurveyCreate"):
        load_erd(path)


def test_enum_class_colliding_with_a_generated_response_schema_rejected(tmp_path):
    path = _enum_erd(
        tmp_path,
        [_entity("Survey", _enum_field("response", ["A", "B"]))],
        ["Survey"],
    )
    with pytest.raises(ERDValidationError, match="SurveyResponse"):
        load_erd(path)


def test_enum_class_colliding_with_an_imported_sqlalchemy_type_name_rejected(tmp_path):
    """entity 'Date' + field 'time' would generate the class 'DateTime', colliding with the
    imported sqlalchemy.DateTime column type."""
    path = _enum_erd(
        tmp_path,
        [_entity("Date", _enum_field("time", ["A", "B"]))],
        ["Date"],
    )
    with pytest.raises(ERDValidationError, match="DateTime"):
        load_erd(path)


def _minimal_external_auth_doc(**overrides):
    doc = {
        "project": {"name": "Demo"},
        "database": {"type": "sqlite", "database_name": "d.db"},
        "auth": {
            "enabled": True,
            "mode": "external",
            "external": {"jwks_url_env_var": "AUTH_JWKS_URL", "issuer": "authservice"},
        },
        "entities": [{"name": "Widget", "fields": [{"name": "id", "type": "integer", "primary_key": True}]}],
        "services": [{"name": "widgets", "entities": ["Widget"]}],
    }
    for key, value in overrides.items():
        doc[key] = value
    return doc


def test_external_auth_minimal_erd_loads_cleanly(tmp_path):
    import yaml

    path = tmp_path / "external.yml"
    path.write_text(yaml.safe_dump(_minimal_external_auth_doc()))
    erd = load_erd(path)
    assert erd.auth.mode == "external"


def test_external_auth_rejects_a_declared_user_entity(tmp_path):
    import yaml

    doc = _minimal_external_auth_doc()
    doc["entities"].append({"name": "User", "fields": [{"name": "id", "type": "integer", "primary_key": True}]})
    doc["services"].append({"name": "auth", "entities": ["User"]})
    path = tmp_path / "external.yml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ERDValidationError, match="User"):
        load_erd(path)


def test_external_auth_without_audience_warns(tmp_path):
    import yaml
    from app.erd.warnings import collect_warnings

    path = tmp_path / "external.yml"
    path.write_text(yaml.safe_dump(_minimal_external_auth_doc()))
    erd = load_erd(path)  # must not raise
    assert any("audience" in w for w in collect_warnings(erd))


def test_external_auth_with_audience_does_not_warn(tmp_path):
    import yaml
    from app.erd.warnings import collect_warnings

    doc = _minimal_external_auth_doc()
    doc["auth"]["external"]["audience"] = "dana-finance"
    path = tmp_path / "external.yml"
    path.write_text(yaml.safe_dump(doc))
    erd = load_erd(path)
    assert not any("audience" in w for w in collect_warnings(erd))


def test_external_auth_rejects_a_relationship_targeting_user_with_no_declared_user_entity(tmp_path):
    """Final review F2: known_entities previously included "User" whenever auth.enabled was
    true, regardless of mode - so a relationship targeting "User" validated cleanly under
    mode: external even though no User table is ever generated there, producing a generated
    app that crashes at startup with a dangling foreign key. The relationship's target must be
    rejected as unknown, the same as targeting any other undeclared entity name."""
    import yaml

    doc = _minimal_external_auth_doc()
    doc["entities"][0]["relationships"] = [
        {"name": "owner", "cardinality": "many-to-one", "target": "User"}
    ]
    path = tmp_path / "external.yml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ERDValidationError, match="User"):
        load_erd(path)


def test_external_auth_rejects_auth_user_rls_identity_source(tmp_path):
    """Final review F2: rls.identity_source.type: auth_user requires a builtin User table to
    resolve ownership from (current_user.id), which doesn't exist under mode: external -
    identity there comes from Principal/jwt_claim instead."""
    import yaml

    doc = _minimal_external_auth_doc()
    doc["entities"].append({"name": "Org", "fields": [{"name": "id", "type": "integer", "primary_key": True}]})
    doc["entities"][0]["relationships"] = [
        {"name": "org", "cardinality": "many-to-one", "target": "Org", "owner": True}
    ]
    doc["entities"][0]["rls"] = {"identity_source": {"type": "auth_user"}}
    doc["services"].append({"name": "orgs", "entities": ["Org"]})
    path = tmp_path / "external.yml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ERDValidationError, match="auth.mode"):
        load_erd(path)


def test_jwt_claim_identity_requires_external_auth_mode(tmp_path):
    import yaml

    doc = {
        "project": {"name": "Demo"},
        "database": {"type": "sqlite", "database_name": "d.db"},
        "entities": [
            {"name": "Agency", "fields": [{"name": "id", "type": "integer", "primary_key": True}]},
            {
                "name": "Project",
                "fields": [{"name": "id", "type": "integer", "primary_key": True}],
                "relationships": [{"name": "agency", "cardinality": "many-to-one", "target": "Agency", "owner": True}],
                "rls": {"identity_source": {"type": "jwt_claim", "claim": "agency_id"}},
            },
        ],
        "services": [{"name": "things", "entities": ["Agency", "Project"]}],
    }
    path = tmp_path / "no_external.yml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ERDValidationError, match="external"):
        load_erd(path)


def _jwt_claim_erd_doc(owner_match_field=None, agency_extra_field=None):
    agency_fields = [{"name": "id", "type": "integer", "primary_key": True}]
    if agency_extra_field:
        agency_fields.append(agency_extra_field)
    rls = {"identity_source": {"type": "jwt_claim", "claim": "agency_id"}}
    if owner_match_field:
        rls["owner_match_field"] = owner_match_field
    return {
        "project": {"name": "Demo"},
        "database": {"type": "sqlite", "database_name": "d.db"},
        "auth": {
            "enabled": True,
            "mode": "external",
            "external": {"jwks_url_env_var": "AUTH_JWKS_URL", "issuer": "authservice"},
        },
        "entities": [
            {"name": "Agency", "fields": agency_fields},
            {
                "name": "Project",
                "fields": [{"name": "id", "type": "integer", "primary_key": True}],
                "relationships": [{"name": "agency", "cardinality": "many-to-one", "target": "Agency", "owner": True}],
                "rls": rls,
            },
        ],
        "services": [{"name": "things", "entities": ["Agency", "Project"]}],
    }


def test_owner_match_field_requires_the_target_field_to_be_unique(tmp_path):
    import yaml

    doc = _jwt_claim_erd_doc(
        owner_match_field="agency_ref",
        agency_extra_field={"name": "agency_ref", "type": "uuid", "unique": False},
    )
    path = tmp_path / "erd.yml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ERDValidationError, match="unique"):
        load_erd(path)


def test_owner_match_field_requires_the_field_to_exist_on_the_owner_entity(tmp_path):
    import yaml

    doc = _jwt_claim_erd_doc(owner_match_field="does_not_exist")
    path = tmp_path / "erd.yml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ERDValidationError, match="does_not_exist"):
        load_erd(path)


@pytest.mark.parametrize("bad_type", ["decimal", "boolean", "float", "text", "json", "datetime"])
def test_owner_match_field_rejects_unsupported_types(tmp_path, bad_type):
    import yaml

    extra = {"name": "agency_ref", "type": bad_type, "unique": True}
    if bad_type == "decimal":
        extra.update({"precision": 10, "scale": 2})
    doc = _jwt_claim_erd_doc(owner_match_field="agency_ref", agency_extra_field=extra)
    path = tmp_path / "erd.yml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ERDValidationError, match="agency_ref"):
        load_erd(path)


@pytest.mark.parametrize("good_type", ["string", "uuid", "integer", "bigint"])
def test_owner_match_field_accepts_supported_types(tmp_path, good_type):
    import yaml

    doc = _jwt_claim_erd_doc(
        owner_match_field="agency_ref",
        agency_extra_field={"name": "agency_ref", "type": good_type, "unique": True},
    )
    path = tmp_path / "erd.yml"
    path.write_text(yaml.safe_dump(doc))
    erd = load_erd(path)  # must not raise
    assert erd.entities[1].rls.owner_match_field == "agency_ref"


def test_owner_match_field_without_jwt_claim_is_rejected(tmp_path):
    import yaml

    doc = {
        "project": {"name": "Demo"},
        "database": {"type": "sqlite", "database_name": "d.db"},
        "auth": {"enabled": True},
        "entities": [
            {"name": "User", "fields": []},
            {
                "name": "Project",
                "fields": [{"name": "id", "type": "integer", "primary_key": True}],
                "relationships": [{"name": "user", "cardinality": "many-to-one", "target": "User", "owner": True}],
                "rls": {"identity_source": {"type": "auth_user"}, "owner_match_field": "email"},
            },
        ],
        "services": [{"name": "things", "entities": ["Project"]}, {"name": "auth", "entities": ["User"]}],
    }
    path = tmp_path / "erd.yml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ERDValidationError, match="owner_match_field"):
        load_erd(path)
