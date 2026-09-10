import pytest
from pydantic import ValidationError

from app.erd.schema import ERDConfig, ALL_ACTIONS, EntitySpec, RelationshipDecl, RLSIdentitySource, RLSSpec


MINIMAL = {
    "project": {"name": "Demo"},
    "database": {"type": "sqlite", "database_name": "demo.db"},
    "entities": [
        {
            "name": "Widget",
            "fields": [
                {"name": "id", "type": "integer", "primary_key": True},
                {"name": "label", "type": "string"},
            ],
        }
    ],
}


def test_minimal_config_parses_with_defaults():
    erd = ERDConfig(**MINIMAL)
    assert erd.project.version == "1.0.0"
    assert erd.auth.enabled is False
    assert erd.rbac.enabled is False
    assert erd.entities[0].endpoints.enabled == ALL_ACTIONS


def test_unknown_endpoint_action_rejected():
    bad = dict(MINIMAL)
    bad["entities"] = [
        {
            "name": "Widget",
            "fields": [{"name": "id", "type": "integer", "primary_key": True}],
            "endpoints": {"enabled": ["create", "explode"]},
        }
    ]
    with pytest.raises(ValidationError):
        ERDConfig(**bad)


def test_unknown_default_permission_action_rejected():
    bad = dict(MINIMAL)
    bad["rbac"] = {"enabled": True, "roles": ["admin"], "default_permissions": {"fly": ["admin"]}}
    with pytest.raises(ValidationError):
        ERDConfig(**bad)


def test_services_block_parses():
    with_services = dict(MINIMAL)
    with_services["services"] = [{"name": "widgets", "entities": ["Widget"]}]
    erd = ERDConfig(**with_services)
    assert erd.services[0].name == "widgets"
    assert erd.services[0].entities == ["Widget"]


def test_services_defaults_to_empty_list():
    erd = ERDConfig(**MINIMAL)
    assert erd.services == []


def test_non_identifier_service_name_rejected():
    bad = dict(MINIMAL)
    bad["services"] = [{"name": "Order Processing", "entities": ["Widget"]}]
    with pytest.raises(ValidationError):
        ERDConfig(**bad)


def test_uppercase_service_name_rejected():
    bad = dict(MINIMAL)
    bad["services"] = [{"name": "Widgets", "entities": ["Widget"]}]
    with pytest.raises(ValidationError):
        ERDConfig(**bad)


def test_database_async_mode_defaults_to_false():
    from app.erd.schema import DatabaseSpec
    spec = DatabaseSpec(type="sqlite", database_name="d.db")
    assert spec.async_mode is False


def test_database_async_mode_can_be_enabled():
    from app.erd.schema import DatabaseSpec
    spec = DatabaseSpec(type="sqlite", database_name="d.db", async_mode=True)
    assert spec.async_mode is True


def test_relationship_owner_and_cascades_ownership_default_false():
    rel = RelationshipDecl(name="user", cardinality="many-to-one", target="User")
    assert rel.owner is False
    assert rel.cascades_ownership is False


def test_relationship_owner_true_accepted_on_many_to_one():
    rel = RelationshipDecl(name="user", cardinality="many-to-one", target="User", owner=True)
    assert rel.owner is True


def test_relationship_owner_true_rejected_on_one_to_many():
    with pytest.raises(ValidationError):
        RelationshipDecl(name="items", cardinality="one-to-many", target="Item", owner=True)


def test_relationship_owner_true_rejected_on_many_to_many():
    with pytest.raises(ValidationError):
        RelationshipDecl(name="tags", cardinality="many-to-many", target="Tag", owner=True)


def test_relationship_cascades_ownership_true_rejected_on_one_to_one():
    with pytest.raises(ValidationError):
        RelationshipDecl(name="profile", cardinality="one-to-one", target="Profile", cascades_ownership=True)


def test_relationship_cannot_be_both_owner_and_cascades_ownership():
    with pytest.raises(ValidationError):
        RelationshipDecl(
            name="user", cardinality="many-to-one", target="User", owner=True, cascades_ownership=True
        )


def test_entity_at_most_one_owner_relationship():
    bad = dict(MINIMAL)
    bad["entities"] = [
        {
            "name": "Order",
            "fields": [{"name": "id", "type": "integer", "primary_key": True}],
            "relationships": [
                {"name": "user", "cardinality": "many-to-one", "target": "User", "owner": True},
                {"name": "agency", "cardinality": "many-to-one", "target": "Agency", "owner": True},
            ],
        }
    ]
    with pytest.raises(ValidationError):
        ERDConfig(**bad)


def test_entity_at_most_one_cascades_ownership_relationship():
    bad = dict(MINIMAL)
    bad["entities"] = [
        {
            "name": "OrderItem",
            "fields": [{"name": "id", "type": "integer", "primary_key": True}],
            "relationships": [
                {"name": "order", "cardinality": "many-to-one", "target": "Order", "cascades_ownership": True},
                {"name": "batch", "cardinality": "many-to-one", "target": "Batch", "cascades_ownership": True},
            ],
        }
    ]
    with pytest.raises(ValidationError):
        ERDConfig(**bad)


def test_rls_identity_source_header_requires_header_name():
    with pytest.raises(ValidationError):
        RLSIdentitySource(type="header")


def test_rls_identity_source_header_rejects_authorization_case_insensitive():
    with pytest.raises(ValidationError):
        RLSIdentitySource(type="header", header_name="authorization")
    with pytest.raises(ValidationError):
        RLSIdentitySource(type="header", header_name="Authorization")
    with pytest.raises(ValidationError):
        RLSIdentitySource(type="header", header_name="AUTHORIZATION")


def test_rls_identity_source_header_accepts_other_names():
    src = RLSIdentitySource(type="header", header_name="X-Tenant-Id")
    assert src.header_name == "X-Tenant-Id"


def test_rls_identity_source_auth_user_does_not_require_header_name():
    src = RLSIdentitySource(type="auth_user")
    assert src.header_name is None


def test_rls_spec_bypass_roles_defaults_empty():
    spec = RLSSpec(identity_source=RLSIdentitySource(type="auth_user"))
    assert spec.bypass_roles == []


def test_entity_rls_defaults_none():
    entity = EntitySpec(name="Widget", fields=[])
    assert entity.rls is None


def test_jwt_spec_new_lifetime_fields_have_correct_defaults():
    from app.erd.schema import JWTSpec
    jwt = JWTSpec()
    assert jwt.expiration_minutes == 30
    assert jwt.refresh_token_expiration_minutes == 10080
    assert jwt.email_verification_expiration_minutes == 1440
    assert jwt.password_reset_expiration_minutes == 30


def test_jwt_spec_new_lifetime_fields_are_overridable():
    from app.erd.schema import JWTSpec
    jwt = JWTSpec(
        refresh_token_expiration_minutes=5,
        email_verification_expiration_minutes=10,
        password_reset_expiration_minutes=1,
    )
    assert jwt.refresh_token_expiration_minutes == 5
    assert jwt.email_verification_expiration_minutes == 10
    assert jwt.password_reset_expiration_minutes == 1


def test_registration_spec_defaults_to_open():
    from app.erd.schema import RegistrationSpec
    reg = RegistrationSpec()
    assert reg.mode == "open"


def test_registration_spec_accepts_valid_modes():
    from app.erd.schema import RegistrationSpec
    assert RegistrationSpec(mode="email_verification").mode == "email_verification"
    assert RegistrationSpec(mode="admin_approval").mode == "admin_approval"


def test_registration_spec_rejects_unknown_mode():
    from app.erd.schema import RegistrationSpec
    with pytest.raises(ValidationError):
        RegistrationSpec(mode="invite_only")


def test_auth_spec_registration_defaults_to_open_mode():
    from app.erd.schema import AuthSpec
    auth = AuthSpec(enabled=True)
    assert auth.registration.mode == "open"
