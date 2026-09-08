from backend.erd.loader import load_erd
from backend.erd.translate import translate

FIXTURES = "backend/tests/fixtures/erd"


def test_translate_minimal():
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    assert state["name"] == "Demo"
    assert state["framework"] == "fastapi"
    assert state["auth_enabled"] is False
    assert state["rbac_enabled"] is False
    assert [m["name"] for m in state["data_models"]] == ["Widget"]

    entity = state["crud_entities"][0]
    assert entity["name"] == "Widget"
    assert entity["plural_snake"] == "widgets"
    assert entity["base_path"] == "/widgets"
    assert entity["enabled_actions"] == ["create", "list", "read", "update", "delete"]
    assert entity["rbac"] == {a: [] for a in ["create", "list", "read", "update", "delete"]}


def test_translate_full_injects_user_and_relationships():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    model_names = {m["name"] for m in state["data_models"]}
    assert model_names == {"Category", "Product", "User"}
    assert state["auth_enabled"] is True
    assert state["rbac_enabled"] is True
    assert state["rbac_roles"] == ["admin", "editor", "viewer"]

    user_model = next(m for m in state["data_models"] if m["name"] == "User")
    user_field_names = {f["name"] for f in user_model["fields"]}
    assert {"id", "email", "password_hash", "roles", "is_active"} <= user_field_names

    product = next(m for m in state["data_models"] if m["name"] == "Product")
    assert len(product["relationships"]) == 1
    rel = product["relationships"][0]
    assert rel["foreign_key"]["model"] == "Product"
    assert rel["foreign_key"]["column"] == "category_id"
    assert rel["foreign_key"]["references"] == "category.id" or rel["foreign_key"]["references"].endswith(".id")

    category = next(m for m in state["data_models"] if m["name"] == "Category")
    assert len(category["relationships"]) == 1  # same relationship appears on both sides

    product_entity = next(e for e in state["crud_entities"] if e["name"] == "Product")
    assert product_entity["rbac"]["create"] == ["admin"]
    assert product_entity["rbac"]["delete"] == ["admin"]
    assert product_entity["rbac"]["read"] == ["admin", "editor", "viewer"]  # from rbac.default_permissions

    assert state["security_config"]["auth_strategy"] == "jwt"
    assert state["security_config"]["jwt_expiration_minutes"] == 30
