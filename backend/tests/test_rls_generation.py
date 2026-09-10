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
