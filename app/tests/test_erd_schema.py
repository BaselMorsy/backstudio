import pytest
from pydantic import ValidationError

from app.erd.schema import (
    ERDConfig,
    ALL_ACTIONS,
    EntitySpec,
    RelationshipDecl,
    RLSIdentitySource,
    RLSSpec,
    ServiceDecl,
)


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


def test_service_prefix_defaults_to_none():
    svc = ServiceDecl(name="catalog", entities=["Widget"])
    assert svc.prefix is None


def test_service_prefix_accepts_valid_value():
    svc = ServiceDecl(name="catalog", entities=["Widget"], prefix="/catalog")
    assert svc.prefix == "/catalog"


@pytest.mark.parametrize(
    "bad_prefix",
    ["catalog", "/catalog/", "", '/cat"alog', "/cat\\alog", "/cat\x00alog"],
    ids=[
        "missing-leading-slash",
        "trailing-slash",
        "empty-string",
        "double-quote",
        "backslash",
        "control-char",
    ],
)
def test_service_prefix_rejects_invalid_values(bad_prefix):
    with pytest.raises(ValidationError):
        ServiceDecl(name="catalog", entities=["Widget"], prefix=bad_prefix)


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


def _with_field(**field):
    doc = dict(MINIMAL)
    doc["entities"] = [
        {
            "name": "Widget",
            "fields": [
                {"name": "id", "type": "integer", "primary_key": True},
                {"name": "f", **field},
            ],
        }
    ]
    return doc


@pytest.mark.parametrize(
    "field",
    [
        {"type": "decimal"},
        {"type": "decimal", "precision": 10},
        {"type": "decimal", "scale": 2},
        {"type": "decimal", "precision": 0, "scale": 0},
        {"type": "decimal", "precision": 4, "scale": 5},
        {"type": "decimal", "precision": 4, "scale": -1},
        {"type": "integer", "precision": 4},
        {"type": "string", "scale": 2},
        {"type": "decimal", "precision": 10, "scale": 2, "primary_key": True},
        {"type": "decimal", "precision": 10, "scale": 2, "default": "abc"},
        {"type": "decimal", "precision": 10, "scale": 2, "default": True},
        {"type": "decimal", "precision": 10, "scale": 2, "default": "NaN"},
        {"type": "enum"},
        {"type": "enum", "values": []},
        {"type": "enum", "values": ["A", "A"]},
        {"type": "enum", "values": ["A", "in-progress"]},
        {"type": "enum", "values": ["class"]},
        {"type": "enum", "values": ["None"]},
        {"type": "enum", "values": ["mro"]},
        {"type": "enum", "values": ["name"]},
        {"type": "enum", "values": ["count"]},
        {"type": "enum", "values": ["_hidden"]},
        {"type": "enum", "values": ["1ST"]},
        {"type": "enum", "values": ["A"], "primary_key": True},
        {"type": "enum", "values": ["A", "B"], "default": "C"},
        {"type": "string", "values": ["A"]},
        {"type": "integer", "timezone": True},
        {"type": "uuid", "default": "not-a-uuid"},
        {"type": "uuid", "default": 123},
    ],
)
def test_invalid_type_specific_attributes_rejected(field):
    with pytest.raises(ValidationError):
        ERDConfig(**_with_field(**field))


def test_valid_new_types_parse():
    erd = ERDConfig(
        **{
            **MINIMAL,
            "entities": [
                {
                    "name": "Ledger",
                    "description": "Append-only ledger",
                    "fields": [
                        {"name": "id", "type": "bigint", "primary_key": True},
                        {"name": "amount", "type": "decimal", "precision": 18, "scale": 2, "default": "0.00", "description": "Minor units"},
                        {"name": "fee", "type": "decimal", "precision": 10, "scale": 4, "default": 0.5},
                        {"name": "n", "type": "decimal", "precision": 5, "scale": 0, "default": 0},
                        {"name": "status", "type": "enum", "values": ["ACTIVE", "DONE"], "default": "ACTIVE"},
                        {"name": "at", "type": "datetime", "timezone": False},
                        {"name": "ref", "type": "uuid"},
                    ],
                }
            ],
        }
    )
    entity = erd.entities[0]
    assert entity.description == "Append-only ledger"
    assert entity.fields[0].type.value == "bigint"
    assert entity.fields[1].description == "Minor units"
    assert entity.fields[5].timezone is False
    assert entity.fields[6].timezone is None


def test_external_auth_requires_the_external_block():
    with pytest.raises(ValidationError):
        from app.erd.schema import AuthSpec
        AuthSpec(mode="external")


def test_external_auth_spec_defaults():
    from app.erd.schema import ExternalAuthSpec
    spec = ExternalAuthSpec(jwks_url_env_var="AUTH_JWKS_URL", issuer="authservice")
    assert spec.algorithms == ["RS256"]
    assert spec.audience is None
    assert spec.claims.subject == "sub"
    assert spec.claims.roles == "roles"


@pytest.mark.parametrize("bad_alg", ["HS256", "HS384", "HS512"])
def test_external_auth_rejects_hmac_algorithms(bad_alg):
    from app.erd.schema import ExternalAuthSpec
    with pytest.raises(ValidationError):
        ExternalAuthSpec(jwks_url_env_var="X", issuer="i", algorithms=[bad_alg])


def test_external_auth_rejects_empty_algorithms():
    from app.erd.schema import ExternalAuthSpec
    with pytest.raises(ValidationError):
        ExternalAuthSpec(jwks_url_env_var="X", issuer="i", algorithms=[])


def test_rls_identity_source_jwt_claim_requires_claim_field():
    from app.erd.schema import RLSIdentitySource
    with pytest.raises(ValidationError):
        RLSIdentitySource(type="jwt_claim")
    source = RLSIdentitySource(type="jwt_claim", claim="agency_id")
    assert source.claim == "agency_id"


def test_rls_identity_source_claim_rejected_on_non_jwt_claim_type():
    from app.erd.schema import RLSIdentitySource
    with pytest.raises(ValidationError):
        RLSIdentitySource(type="auth_user", claim="agency_id")
    with pytest.raises(ValidationError):
        RLSIdentitySource(type="header", header_name="X-Tenant-Id", claim="agency_id")


def test_rls_header_name_still_rejected_on_jwt_claim_type():
    from app.erd.schema import RLSIdentitySource
    with pytest.raises(ValidationError):
        RLSIdentitySource(type="jwt_claim", claim="agency_id", header_name="X-Tenant-Id")
