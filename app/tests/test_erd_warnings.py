import glob

import pytest

from app.erd.loader import load_erd
from app.erd.schema import ERDConfig
from app.erd.warnings import collect_warnings


def _erd(entities, auth=False):
    return ERDConfig(
        **{
            "project": {"name": "Demo"},
            "database": {"type": "sqlite", "database_name": "d.db"},
            "auth": {"enabled": auth},
            "entities": entities,
        }
    )


def _entity(name, relationships=()):
    return {
        "name": name,
        "fields": [{"name": "id", "type": "integer", "primary_key": True}],
        "relationships": list(relationships),
    }


def _rel(name, target, cardinality="many-to-one", **extra):
    return {"name": name, "cardinality": cardinality, "target": target, **extra}


def test_many_to_one_with_an_ignored_name_warns_about_attribute_and_fk_column():
    warnings = collect_warnings(_erd([_entity("Person"), _entity("Order", [_rel("customer", "Person")])]))
    assert len(warnings) == 1
    message = warnings[0]
    assert message.startswith("Order.customer -> Person: declared name 'customer' is not used")
    assert "the attribute is 'person'" in message
    assert "the foreign key column is 'person_id'" in message
    assert "'attribute:' / 'foreign_key_column:'" in message


def test_a_name_that_matches_the_derived_one_does_not_warn():
    assert collect_warnings(_erd([_entity("Person"), _entity("Order", [_rel("person", "Person")])])) == []


def test_one_to_many_and_many_to_many_only_compare_the_attribute():
    """Review Focus: the FK column of a one-to-many is derived from the *entity* (category_id),
    never from the relationship name - comparing it would warn on a perfectly named relationship."""
    entities = [_entity("Post"), _entity("Label"), _entity("Category", [
        _rel("posts", "Post", "one-to-many"),
        _rel("labels", "Label", "many-to-many"),
    ])]
    assert collect_warnings(_erd(entities)) == []

    warnings = collect_warnings(_erd([_entity("Post"), _entity("Category", [_rel("items", "Post", "one-to-many")])]))
    assert len(warnings) == 1
    assert "the attribute is 'posts'" in warnings[0] and "foreign key column" not in warnings[0]

    warnings = collect_warnings(_erd([_entity("Label"), _entity("Category", [_rel("tags", "Label", "many-to-many")])]))
    assert len(warnings) == 1 and "the attribute is 'labels'" in warnings[0]


def test_two_relationships_to_the_same_target_honor_their_names_so_no_warning():
    entities = [_entity("Person"), _entity("Message", [_rel("sender", "Person"), _rel("recipient", "Person")])]
    assert collect_warnings(_erd(entities)) == []


def test_explicit_overrides_silence_the_warning_for_what_they_cover():
    both = _rel("customer", "Person", attribute="customer", foreign_key_column="customer_id")
    assert collect_warnings(_erd([_entity("Person"), _entity("Order", [both])])) == []

    only_attribute = _rel("customer", "Person", attribute="customer")
    warnings = collect_warnings(_erd([_entity("Person"), _entity("Order", [only_attribute])]))
    assert len(warnings) == 1
    assert "foreign key column is 'person_id'" in warnings[0] and "the attribute is" not in warnings[0]


def test_self_referential_and_declared_user_relationships_never_warn():
    assert collect_warnings(_erd([_entity("Employee", [_rel("boss", "Employee")])])) == []
    assert collect_warnings(_erd([_entity("User", [_rel("whatever", "Person")]), _entity("Person")], auth=True)) == []


def test_ecommerce_example_warns_exactly_for_its_two_user_relationships():
    warnings = collect_warnings(load_erd("examples/ecommerce.yml"))
    assert sorted(w.split(":")[0] for w in warnings) == ["Order.customer -> User", "Review.reviewer -> User"]


@pytest.mark.parametrize("path", sorted(glob.glob("app/tests/fixtures/erd/*.yml")))
def test_no_test_fixture_produces_a_warning(path):
    assert collect_warnings(load_erd(path)) == []
