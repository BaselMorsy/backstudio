import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_root_owned_repo_functions_gain_owner_id_and_where(tmp_path):
    erd = load_erd(f"{FIXTURES}/rls_root_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    ast.parse(repo_src)

    get_by_id_start = repo_src.index("def get_order_by_id(")
    get_by_id_end = repo_src.index("\ndef get_all_orders(")
    get_by_id_src = repo_src[get_by_id_start:get_by_id_end]
    assert "owner_id: Optional[int] = None" in get_by_id_src
    assert "if owner_id is not None:" in get_by_id_src
    assert "Order.user_id == owner_id" in get_by_id_src

    get_all_start = repo_src.index("def get_all_orders(")
    get_all_end = repo_src.index("\ndef update_order(")
    get_all_src = repo_src[get_all_start:get_all_end]
    assert "owner_id: Optional[int] = None" in get_all_src
    assert "Order.user_id == owner_id" in get_all_src

    update_start = repo_src.index("def update_order(")
    update_end = repo_src.index("\ndef delete_order(")
    update_src = repo_src[update_start:update_end]
    assert "owner_id: Optional[int] = None" in update_src
    assert "get_order_by_id(db, order_id, owner_id=owner_id)" in update_src

    delete_start = repo_src.index("def delete_order(")
    delete_src = repo_src[delete_start:]
    assert "owner_id: Optional[int] = None" in delete_src
    assert "get_order_by_id(db, order_id, owner_id=owner_id)" in delete_src

    # create_order must be completely untouched - no owner_id parameter anywhere near it
    create_start = repo_src.index("def create_order(")
    create_end = repo_src.index("\ndef get_order_by_id(")
    create_src = repo_src[create_start:create_end]
    assert "owner_id" not in create_src


def test_entity_without_rls_gets_no_owner_id_parameter(tmp_path):
    """valid_full.yml's Product/Category have owned_relationships but no owner:true/
    cascades_ownership:true anywhere - their repo functions must be byte-identical to
    before this task, proving RLS involvement is genuinely opt-in per entity.
    """
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    assert "owner_id" not in repo_src


def test_root_owned_filtering_actually_works_against_a_real_db(tmp_path):
    """Live proof: two orders, two different owners, owner_id=None sees both, a real
    owner_id sees only its own, and a non-owner's update/delete both no-op (return
    None/False) rather than touching the other owner's row - the 404-not-403 guarantee
    falls out of get_by_id's own filtering, this proves it end to end at the repo layer.
    """
    erd = load_erd(f"{FIXTURES}/rls_root_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_root_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        repo = importlib.import_module("database.repo")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            owner1 = service.register_user(db, "owner1@example.com", "supersecret123")
            owner2 = service.register_user(db, "owner2@example.com", "supersecret123")

            order1 = repo.create_order(db, {"status": "pending", "user_id": owner1.id})
            order2 = repo.create_order(db, {"status": "pending", "user_id": owner2.id})

            # owner_id=None (bypass) sees both
            assert {o.id for o in repo.get_all_orders(db)} == {order1.id, order2.id}

            # each owner's owner_id sees only their own
            assert [o.id for o in repo.get_all_orders(db, owner_id=owner1.id)] == [order1.id]
            assert [o.id for o in repo.get_all_orders(db, owner_id=owner2.id)] == [order2.id]

            # owner1 can fetch their own order, not owner2's
            assert repo.get_order_by_id(db, order1.id, owner_id=owner1.id) is not None
            assert repo.get_order_by_id(db, order2.id, owner_id=owner1.id) is None

            # owner1 cannot update or delete owner2's order
            assert repo.update_order(db, order2.id, {"status": "shipped"}, owner_id=owner1.id) is None
            assert repo.delete_order(db, order2.id, owner_id=owner1.id) is False
            # ... and owner2's order is genuinely untouched
            untouched = repo.get_order_by_id(db, order2.id, owner_id=owner2.id)
            assert untouched.status == "pending"

            # owner1 CAN update/delete their own
            updated = repo.update_order(db, order1.id, {"status": "shipped"}, owner_id=owner1.id)
            assert updated.status == "shipped"
            assert repo.delete_order(db, order1.id, owner_id=owner1.id) is True
            assert repo.get_order_by_id(db, order1.id) is None
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_cascade_owned_repo_functions_render_join_chain(tmp_path):
    erd = load_erd(f"{FIXTURES}/rls_cascade_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    ast.parse(repo_src)

    one_hop_start = repo_src.index("def get_order_item_by_id(")
    one_hop_end = repo_src.index("\ndef get_all_order_items(")
    one_hop_src = repo_src[one_hop_start:one_hop_end]
    assert "query.join(Order, OrderItem.order_id == Order.id)" in one_hop_src
    assert "Order.user_id == owner_id" in one_hop_src

    two_hop_start = repo_src.index("def get_order_line_discount_by_id(")
    two_hop_end = repo_src.index("\ndef get_all_order_line_discounts(")
    two_hop_src = repo_src[two_hop_start:two_hop_end]
    assert "query.join(OrderItem, OrderLineDiscount.order_item_id == OrderItem.id)" in two_hop_src
    assert "query.join(Order, OrderItem.order_id == Order.id)" in two_hop_src
    assert "Order.user_id == owner_id" in two_hop_src

    # Category is not reachable from any owner:true entity - completely unaffected
    category_start = repo_src.index("def get_category_by_id(")
    category_end = repo_src.index("\ndef get_all_categories(")
    assert "owner_id" not in repo_src[category_start:category_end]


def test_cascade_owned_filtering_actually_works_against_a_real_db_at_two_hops(tmp_path):
    """Live proof at both hop depths in one flow: two owners, each with their own Order ->
    OrderItem -> OrderLineDiscount chain; owner_id correctly isolates each owner's full
    chain at every depth, and Category (unrelated) never takes an owner_id at all.
    """
    erd = load_erd(f"{FIXTURES}/rls_cascade_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_cascade_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        repo = importlib.import_module("database.repo")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            owner1 = service.register_user(db, "owner1@example.com", "supersecret123")
            owner2 = service.register_user(db, "owner2@example.com", "supersecret123")

            order1 = repo.create_order(db, {"status": "pending", "user_id": owner1.id})
            order2 = repo.create_order(db, {"status": "pending", "user_id": owner2.id})

            item1 = repo.create_order_item(db, {"quantity": 1, "order_id": order1.id})
            item2 = repo.create_order_item(db, {"quantity": 1, "order_id": order2.id})

            discount1 = repo.create_order_line_discount(db, {"percent_off": 10.0, "order_item_id": item1.id})
            discount2 = repo.create_order_line_discount(db, {"percent_off": 10.0, "order_item_id": item2.id})

            # 1-hop: owner_id isolates each owner's OrderItem
            assert [i.id for i in repo.get_all_order_items(db, owner_id=owner1.id)] == [item1.id]
            assert repo.get_order_item_by_id(db, item2.id, owner_id=owner1.id) is None
            assert repo.get_order_item_by_id(db, item1.id, owner_id=owner1.id) is not None

            # 2-hop: owner_id isolates each owner's OrderLineDiscount
            assert [d.id for d in repo.get_all_order_line_discounts(db, owner_id=owner1.id)] == [discount1.id]
            assert repo.get_order_line_discount_by_id(db, discount2.id, owner_id=owner1.id) is None
            assert repo.get_order_line_discount_by_id(db, discount1.id, owner_id=owner1.id) is not None

            # owner1 cannot delete owner2's OrderLineDiscount via the 2-hop chain
            assert repo.delete_order_line_discount(db, discount2.id, owner_id=owner1.id) is False
            assert repo.get_order_line_discount_by_id(db, discount2.id, owner_id=owner2.id) is not None
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_root_owned_create_injects_owner_id_overriding_client_value(tmp_path):
    erd = load_erd(f"{FIXTURES}/rls_root_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "orders" / "service.py").read_text(encoding="utf-8")
    ast.parse(service_src)

    create_start = service_src.index("def create_order(")
    create_end = service_src.index("\n    def list_orders(")
    create_src = service_src[create_start:create_end]
    assert "owner_id: Optional[int] = None" in create_src
    assert 'data["user_id"] = owner_id' in create_src
    # no FK-existence validation is rendered for the owner relationship itself
    assert "get_user_by_id" not in create_src


def test_root_owned_create_service_actually_ignores_client_supplied_owner(tmp_path):
    """A client-supplied user_id in the payload must be silently overridden by the
    resolved owner_id - proves this at runtime, not just via string assertions.
    """
    erd = load_erd(f"{FIXTURES}/rls_root_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_service_create_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")
        orders_service = importlib.import_module("modules.orders.service")

        database_base.init_db()
        auth = auth_service.get_auth_service()
        orders = orders_service.get_orders_service()
        db = database_base.SessionLocal()
        try:
            real_owner = auth.register_user(db, "real@example.com", "supersecret123")
            attacker_id = real_owner.id + 999  # doesn't even need to exist - never looked up

            order = orders.create_order(db, {"status": "pending", "user_id": attacker_id}, owner_id=real_owner.id)
            assert order.user_id == real_owner.id
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_cascade_owned_create_validates_parent_ownership(tmp_path):
    erd = load_erd(f"{FIXTURES}/rls_cascade_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "ordering" / "service.py").read_text(encoding="utf-8")
    create_start = service_src.index("def create_order_item(")
    create_end = service_src.index("\n    def list_order_items(")
    create_src = service_src[create_start:create_end]
    assert "owner_id: Optional[int] = None" in create_src
    assert 'repo.get_order_by_id(db, data["order_id"], owner_id=owner_id) is None' in create_src


def test_cascade_owned_create_actually_rejects_an_unowned_parent(tmp_path):
    import pytest as _pytest

    erd = load_erd(f"{FIXTURES}/rls_cascade_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_cascade_create_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")
        ordering_service = importlib.import_module("modules.ordering.service")

        database_base.init_db()
        auth = auth_service.get_auth_service()
        ordering = ordering_service.get_ordering_service()
        db = database_base.SessionLocal()
        try:
            owner1 = auth.register_user(db, "owner1@example.com", "supersecret123")
            owner2 = auth.register_user(db, "owner2@example.com", "supersecret123")
            order2 = ordering.create_order(db, {"status": "pending"}, owner_id=owner2.id)

            # owner1 tries to attach an OrderItem to owner2's (real, existing) order
            with _pytest.raises(ValueError):
                ordering.create_order_item(db, {"quantity": 1, "order_id": order2.id}, owner_id=owner1.id)

            # a genuinely nonexistent order_id gets the same ValueError
            with _pytest.raises(ValueError):
                ordering.create_order_item(db, {"quantity": 1, "order_id": 999999}, owner_id=owner1.id)

            # owner2 can attach an OrderItem to their own order
            item = ordering.create_order_item(db, {"quantity": 1, "order_id": order2.id}, owner_id=owner2.id)
            assert item.order_id == order2.id
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_update_reassigning_cascade_linking_fk_validates_new_parent_ownership(tmp_path):
    """Changing OrderItem.order_id via update must revalidate the NEW order_id's
    ownership, not just the original creation-time value.
    """
    import pytest as _pytest

    erd = load_erd(f"{FIXTURES}/rls_cascade_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    db_path = tmp_path / "rls_cascade_update_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        auth_service = importlib.import_module("modules.auth.service")
        ordering_service = importlib.import_module("modules.ordering.service")

        database_base.init_db()
        auth = auth_service.get_auth_service()
        ordering = ordering_service.get_ordering_service()
        db = database_base.SessionLocal()
        try:
            owner1 = auth.register_user(db, "owner1@example.com", "supersecret123")
            owner2 = auth.register_user(db, "owner2@example.com", "supersecret123")
            order1 = ordering.create_order(db, {"status": "pending"}, owner_id=owner1.id)
            order2 = ordering.create_order(db, {"status": "pending"}, owner_id=owner2.id)
            item = ordering.create_order_item(db, {"quantity": 1, "order_id": order1.id}, owner_id=owner1.id)

            with _pytest.raises(ValueError):
                ordering.update_order_item(db, item.id, {"order_id": order2.id}, owner_id=owner1.id)
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_entity_without_rls_service_methods_unchanged(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    service_src = (codebase_dir / "modules" / "catalog" / "service.py").read_text(encoding="utf-8")
    assert "owner_id" not in service_src


def test_cascade_owner_id_composes_with_an_existing_owned_relationship_filter(tmp_path):
    """OrderItem.product_id (an ordinary owned_relationship, unrelated to ownership) and
    OrderItem's RLS owner_id filter (via its cascades_ownership chain to Order) must both
    apply in the same get_all_order_items() call - two ANDed WHERE clauses, not one
    overwriting the other.
    """
    erd = load_erd(f"{FIXTURES}/rls_cascade_composability.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    get_all_start = repo_src.index("def get_all_order_items(")
    get_all_end = repo_src.index("\ndef update_order_item(")
    get_all_src = repo_src[get_all_start:get_all_end]
    assert "product_id: Optional[int] = None" in get_all_src
    assert "owner_id: Optional[int] = None" in get_all_src
    assert "OrderItem.product_id == product_id" in get_all_src
    assert "Order.user_id == owner_id" in get_all_src

    db_path = tmp_path / "rls_composability_test.db"

    import sys
    sys.path.insert(0, str(codebase_dir))
    try:
        import importlib
        import os
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["JWT_SECRET"] = "test-only-secret-do-not-use-in-production"
        os.environ["DEBUG"] = "True"

        database_base = importlib.import_module("database.base")
        repo = importlib.import_module("database.repo")
        auth_service = importlib.import_module("modules.auth.service")

        database_base.init_db()
        service = auth_service.get_auth_service()
        db = database_base.SessionLocal()
        try:
            owner1 = service.register_user(db, "owner1@example.com", "supersecret123")
            product_a = repo.create_product(db, {"name": "A"})
            product_b = repo.create_product(db, {"name": "B"})
            order1 = repo.create_order(db, {"status": "pending", "user_id": owner1.id})

            item_a = repo.create_order_item(db, {"quantity": 1, "order_id": order1.id, "product_id": product_a.id})
            repo.create_order_item(db, {"quantity": 1, "order_id": order1.id, "product_id": product_b.id})

            # both filters together narrow to exactly one row
            filtered = repo.get_all_order_items(db, owner_id=owner1.id, product_id=product_a.id)
            assert [i.id for i in filtered] == [item_a.id]
        finally:
            db.close()
    finally:
        sys.path.remove(str(codebase_dir))
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("JWT_SECRET", None)
        os.environ.pop("DEBUG", None)
        for mod_name in list(sys.modules):
            if mod_name == "database" or mod_name.startswith("database.") or mod_name == "modules" or mod_name.startswith("modules.") or mod_name == "config":
                sys.modules.pop(mod_name, None)


def test_rbac_gated_rls_entity_uses_current_user_as_named_param(tmp_path):
    """rls_root_owned.yml: Order.rls.bypass_roles=[admin], every action RBAC-gated
    ([admin, customer]) - current_user must be a named Depends(require_roles(...))
    parameter, and the decorator's separate dependencies=[] line must be suppressed
    for create (no double-evaluation of require_roles).
    """
    erd = load_erd(f"{FIXTURES}/rls_root_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "orders" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)

    create_start = routes_src.index('@router.post(\n    "/orders"')
    create_end = routes_src.index("\n@router.get(")
    create_src = routes_src[create_start:create_end]
    assert "dependencies=[Depends(require_roles(" not in create_src
    assert "current_user: User = Depends(require_roles(" in create_src
    assert "owner_id = None if set(current_user.roles or []).intersection(" in create_src
    assert '["admin"]' in create_src  # bypass_roles rendered into the intersection call
    assert "owner_id=owner_id" in create_src


def test_rbac_disabled_rls_entity_uses_get_current_user_fallback(tmp_path):
    erd = load_erd(f"{FIXTURES}/rls_no_rbac_action.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "notes" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "from database.models import User" in routes_src
    assert "current_user: User = Depends(_auth_service.get_current_user)" in routes_src
    assert "Depends(require_roles(" not in routes_src  # RBAC disabled - never rendered at all
    assert "owner_id = None if set(current_user.roles or []).intersection([])" in routes_src


def test_header_sourced_rls_entity_uses_header_param_not_current_user(tmp_path):
    erd = load_erd(f"{FIXTURES}/rls_header_owned.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "orders" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)
    assert "from fastapi import" in routes_src and "Header" in routes_src
    assert 'rls_owner_header: int = Header(..., alias="X-Tenant-Id")' in routes_src
    assert "current_user" not in routes_src
    assert "from database.models import User" not in routes_src
    assert "owner_id = rls_owner_header" in routes_src

    tenants_src = (codebase_dir / "modules" / "tenants" / "routes.py").read_text(encoding="utf-8")
    assert "owner_id" not in tenants_src  # Tenant itself carries no rls - only Order does


def test_entity_without_rls_routes_unchanged(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "catalog" / "routes.py").read_text(encoding="utf-8")
    assert "owner_id" not in routes_src
    assert "rls_owner_header" not in routes_src
    assert "current_user" not in routes_src


def test_header_sourced_rls_entity_with_rbac_keeps_decorator_dependency_and_header_param(tmp_path):
    """rls_header_owned_with_rbac.yml: Order is RLS header-sourced AND RBAC-gated on every
    action - the decorator-suppression logic only ever fires for auth_user-sourced RLS
    (see the design note in the task-7 brief), so here the decorator's
    dependencies=[Depends(require_roles(...))] must render normally (NOT suppressed), while
    the route also gets rls_owner_header (never current_user) - RBAC gates the action, the
    header still independently governs ownership.
    """
    erd = load_erd(f"{FIXTURES}/rls_header_owned_with_rbac.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "orders" / "routes.py").read_text(encoding="utf-8")
    ast.parse(routes_src)

    create_start = routes_src.index('@router.post(\n    "/orders"')
    create_end = routes_src.index("\n@router.get(")
    create_src = routes_src[create_start:create_end]
    assert "dependencies=[Depends(require_roles(" in create_src
    assert 'rls_owner_header: int = Header(..., alias="X-Tenant-Id")' in create_src
    assert "current_user" not in create_src
    assert "owner_id = rls_owner_header" in create_src

    # current_user must never appear anywhere in this file - Order is entirely header-sourced
    assert "current_user" not in routes_src
    assert "from database.models import User" not in routes_src


def test_list_route_excludes_rls_link_from_client_query_params(tmp_path):
    """rls_cascade_composability.yml: OrderItem's rls-link (order_id, cascades_ownership)
    must NOT appear as a client-supplied ?order_id= query param on list_order_items_route,
    even though it's still a normal owned_relationships entry at the repo/service layer -
    only the OTHER owned_relationship (product_id) should appear as a query param.
    """
    erd = load_erd(f"{FIXTURES}/rls_cascade_composability.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    routes_src = (codebase_dir / "modules" / "ordering" / "routes.py").read_text(encoding="utf-8")
    list_start = routes_src.index("def list_order_item_route(")
    list_end = routes_src.index("\n@router.get(", list_start)
    list_src = routes_src[list_start:list_end]
    assert "product_id: Optional[int] = Query(None)" in list_src
    assert "order_id: Optional[int] = Query(None)" not in list_src
