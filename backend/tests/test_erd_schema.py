import pytest
from pydantic import ValidationError

from backend.erd.schema import ERDConfig, ALL_ACTIONS


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
