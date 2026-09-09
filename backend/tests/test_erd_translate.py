import pytest

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.erd.schema import (
    ERDConfig,
    ProjectMeta,
    DatabaseSpec,
    EntitySpec,
    RelationshipDecl,
    EndpointSpec,
    AuthSpec,
    ServiceDecl,
)
from backend.schemas.data import ModelField, FieldType

FIXTURES = "backend/tests/fixtures/erd"


def test_translate_minimal():
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    assert state["name"] == "Demo"
    assert state["framework"] == "fastapi"
    assert state["auth_enabled"] is False
    assert state["rbac_enabled"] is False
    assert [m["name"] for m in state["data_models"]] == ["Widget"]

    entity = state["modules"][0]["entities"][0]
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

    catalog_module = next(m for m in state["modules"] if m["name"] == "catalog")
    product_entity = next(e for e in catalog_module["entities"] if e["name"] == "Product")
    assert product_entity["rbac"]["create"] == ["admin"]
    assert product_entity["rbac"]["delete"] == ["admin"]
    assert product_entity["rbac"]["read"] == ["admin", "editor", "viewer"]  # from rbac.default_permissions

    assert state["security_config"]["auth_strategy"] == "jwt"
    assert state["security_config"]["jwt_expiration_minutes"] == 30


def test_translate_one_to_many_cardinality():
    """Test one-to-many relationship: Author declares one-to-many to Book.

    FK should live on the target entity (Book), not the source (Author).
    Relationship should appear on both Author and Book.
    """
    erd = ERDConfig(
        project=ProjectMeta(name="Library", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="library.db"),
        entities=[
            EntitySpec(
                name="Author",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(
                        name="author_books",
                        cardinality="one-to-many",
                        target="Book"
                    )
                ]
            ),
            EntitySpec(
                name="Book",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]
            ),
        ]
    )

    state = translate(erd)
    model_names = {m["name"] for m in state["data_models"]}
    assert model_names == {"Author", "Book"}

    # Get the relationship from the state
    author_rels = next(m for m in state["data_models"] if m["name"] == "Author")["relationships"]
    book_rels = next(m for m in state["data_models"] if m["name"] == "Book")["relationships"]

    # Should have exactly one relationship
    assert len(author_rels) == 1
    assert len(book_rels) == 1

    # Both should refer to the same relationship
    rel = author_rels[0]
    assert rel["cardinality"] == "one-to-many"

    # For one-to-many, FK lives on the TARGET (Book)
    assert rel["foreign_key"]["model"] == "Book", "FK should live on the target entity (Book)"
    assert rel["foreign_key"]["column"] == "author_id"
    assert rel["foreign_key"]["references"] == "authors.id"

    # Relationship should appear on both sides
    assert rel in book_rels, "Relationship should appear on both Author and Book"


def test_translate_one_to_one_cardinality():
    """Test one-to-one relationship: Author declares one-to-one to Profile.

    FK should live on the source entity (Author), and unique should be True.
    Relationship should appear on both Author and Profile.
    """
    erd = ERDConfig(
        project=ProjectMeta(name="SocialMedia", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="social.db"),
        entities=[
            EntitySpec(
                name="Author",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(
                        name="author_profile",
                        cardinality="one-to-one",
                        target="Profile"
                    )
                ]
            ),
            EntitySpec(
                name="Profile",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]
            ),
        ]
    )

    state = translate(erd)
    model_names = {m["name"] for m in state["data_models"]}
    assert model_names == {"Author", "Profile"}

    # Get the relationship from the state
    author_rels = next(m for m in state["data_models"] if m["name"] == "Author")["relationships"]
    profile_rels = next(m for m in state["data_models"] if m["name"] == "Profile")["relationships"]

    # Should have exactly one relationship
    assert len(author_rels) == 1
    assert len(profile_rels) == 1

    # Both should refer to the same relationship
    rel = author_rels[0]
    assert rel["cardinality"] == "one-to-one"

    # For one-to-one, FK lives on the SOURCE (Author)
    assert rel["foreign_key"]["model"] == "Author", "FK should live on the source entity (Author)"
    assert rel["foreign_key"]["column"] == "profile_id"
    assert rel["foreign_key"]["references"] == "profiles.id"

    # unique should be True for one-to-one
    assert rel["foreign_key"]["unique"] is True, "one-to-one FK should have unique=True"

    # Relationship should appear on both sides
    assert rel in profile_rels, "Relationship should appear on both Author and Profile"


def test_translate_many_to_many_cardinality():
    """Test many-to-many relationship: Author declares many-to-many to Tag.

    Should produce an association_table with left and right foreign keys.
    Relationship should appear on both Author and Tag.
    """
    erd = ERDConfig(
        project=ProjectMeta(name="BlogSystem", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="blog.db"),
        entities=[
            EntitySpec(
                name="Author",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(
                        name="author_tags",
                        cardinality="many-to-many",
                        target="Tag"
                    )
                ]
            ),
            EntitySpec(
                name="Tag",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]
            ),
        ]
    )

    state = translate(erd)
    model_names = {m["name"] for m in state["data_models"]}
    assert model_names == {"Author", "Tag"}

    # Get the relationship from the state
    author_rels = next(m for m in state["data_models"] if m["name"] == "Author")["relationships"]
    tag_rels = next(m for m in state["data_models"] if m["name"] == "Tag")["relationships"]

    # Should have exactly one relationship
    assert len(author_rels) == 1
    assert len(tag_rels) == 1

    # Both should refer to the same relationship
    rel = author_rels[0]
    assert rel["cardinality"] == "many-to-many"

    # For many-to-many, should have association_table, not foreign_key
    assert "association_table" in rel, "many-to-many should have association_table"
    assert "foreign_key" not in rel, "many-to-many should not have foreign_key"

    assoc = rel["association_table"]
    assert "table_name" in assoc
    assert "left_foreign_key" in assoc
    assert "right_foreign_key" in assoc

    # Left FK should reference Author
    left_fk = assoc["left_foreign_key"]
    assert left_fk["model"] == "Author"
    assert left_fk["column"] == "author_id"
    assert left_fk["references"] == "authors.id"

    # Right FK should reference Tag
    right_fk = assoc["right_foreign_key"]
    assert right_fk["model"] == "Tag"
    assert right_fk["column"] == "tag_id"
    assert right_fk["references"] == "tags.id"

    # Relationship should appear on both sides
    assert rel in tag_rels, "Relationship should appear on both Author and Tag"


def test_translate_two_relationships_to_same_target_stay_distinct():
    """Regression test: Message has both a 'sender' and a 'recipient' many-to-one
    relationship, both targeting Person. Before the fix, both derived their
    attribute name and FK column purely from the target ('person'/'person_id'),
    so the second silently overwrote the first in the generated SQLAlchemy class.
    Both relationships must now survive translation with distinct names.
    """
    erd = ERDConfig(
        project=ProjectMeta(name="Messenger", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="messenger.db"),
        entities=[
            EntitySpec(
                name="Person",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
            EntitySpec(
                name="Message",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="sender", cardinality="many-to-one", target="Person"),
                    RelationshipDecl(name="recipient", cardinality="many-to-one", target="Person"),
                ],
            ),
        ],
    )

    state = translate(erd)

    message_rels = next(m for m in state["data_models"] if m["name"] == "Message")["relationships"]
    assert len(message_rels) == 2

    sender_rel = next(r for r in message_rels if r["name"] == "sender")
    recipient_rel = next(r for r in message_rels if r["name"] == "recipient")

    # Distinct attribute names on Message.
    assert sender_rel["source"]["attribute"] != recipient_rel["source"]["attribute"]
    assert sender_rel["source"]["attribute"] == "sender"
    assert recipient_rel["source"]["attribute"] == "recipient"

    # Distinct FK columns on Message.
    assert sender_rel["foreign_key"]["column"] != recipient_rel["foreign_key"]["column"]
    assert sender_rel["foreign_key"]["column"] == "sender_id"
    assert recipient_rel["foreign_key"]["column"] == "recipient_id"
    assert sender_rel["foreign_key"]["model"] == "Message"
    assert recipient_rel["foreign_key"]["model"] == "Message"

    # Distinct back-reference attribute names on Person.
    person_rels = next(m for m in state["data_models"] if m["name"] == "Person")["relationships"]
    assert len(person_rels) == 2
    person_attrs = {r["target"]["attribute"] for r in person_rels}
    assert len(person_attrs) == 2

    # Rendering must not raise (both relationships coexist on the SQLAlchemy class).
    import tempfile
    import ast as ast_module

    from backend.services.code_generator import CodeGenerator

    with tempfile.TemporaryDirectory() as tmp:
        gen = CodeGenerator(output_dir=tmp)
        codebase = gen.generate_project(state, force=True)
        models_src = (codebase / "database" / "models.py").read_text(encoding="utf-8")
        ast_module.parse(models_src)
        assert "sender" in models_src
        assert "recipient" in models_src


def test_translate_ambiguous_relationship_names_raise_clear_error():
    """If both relationships were given the SAME explicit attribute name, translation
    must fail loudly instead of silently letting one clobber the other.
    """
    from backend.erd.loader import ERDValidationError

    erd = ERDConfig(
        project=ProjectMeta(name="Messenger", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="messenger.db"),
        entities=[
            EntitySpec(
                name="Person",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
            EntitySpec(
                name="Message",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(
                        name="sender", cardinality="many-to-one", target="Person", attribute="contact"
                    ),
                    RelationshipDecl(
                        name="recipient", cardinality="many-to-one", target="Person", attribute="contact"
                    ),
                ],
            ),
        ],
    )

    with pytest.raises(ERDValidationError, match="both derive the attribute name"):
        translate(erd)


def test_translate_field_types_are_strings_not_enums():
    """Regression test: ensure FieldType enums are serialized to strings, not enum instances.

    This prevents a critical bug where Pydantic v2's default mode='python' would produce
    FieldType enum instances (e.g. FieldType.FLOAT), which then serialize as "fieldtype.float"
    when str() is called, breaking SQLAlchemy type mapping in _get_sqlalchemy_type().
    The fix is to use model_dump(mode='json') to serialize enums to their string values.
    """
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    # Check Product model fields
    product_model = next(m for m in state["data_models"] if m["name"] == "Product")
    for field in product_model["fields"]:
        assert isinstance(field["type"], str), (
            f"Field {field['name']} type should be a string, not {type(field['type']).__name__}: {repr(field['type'])}"
        )
        # Verify no enum repr in the string
        assert not str(field["type"]).lower().startswith("fieldtype."), (
            f"Field {field['name']} type should not be enum repr: {field['type']}"
        )

    # Verify a specific non-string type is correct
    id_field = next(f for f in product_model["fields"] if f["name"] == "id")
    assert id_field["type"] == "integer", f"id should be 'integer', got {repr(id_field['type'])}"

    # Verify database type is also a string, not an enum
    assert isinstance(state["database_config"]["type"], str), (
        f"database type should be string, got {type(state['database_config']['type']).__name__}"
    )
    assert state["database_config"]["type"] == "postgresql", (
        f"database type should be 'postgresql', got {repr(state['database_config']['type'])}"
    )

    # Check module-grouped entity fields as well
    catalog_module = next(m for m in state["modules"] if m["name"] == "catalog")
    product_entity = next(e for e in catalog_module["entities"] if e["name"] == "Product")
    for field in product_entity["fields"]:
        assert isinstance(field["type"], str), (
            f"Module entity field {field['name']} type should be string, got {type(field['type']).__name__}"
        )


def test_translate_relationship_enums_to_strings():
    """Regression test: ensure Cardinality and LazyStrategy enums are serialized to strings.

    This prevents a bug where rel.cardinality and rel.lazy enum instances would be embedded
    in the relationship dict, causing Jinja templates to call str() on them (producing
    "Cardinality.MANY_TO_ONE" instead of "many-to-one", or "LazyStrategy.SELECTIN" instead
    of "selectin"), breaking SQLAlchemy relationship() call generation.
    The fix is to use .value to extract the string representation.
    """
    from backend.schemas.data import LazyStrategy

    # Create an ERDConfig with a relationship that has lazy set
    erd = ERDConfig(
        project=ProjectMeta(name="TestLazy", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="test.db"),
        entities=[
            EntitySpec(
                name="Author",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(
                        name="author_books",
                        cardinality="one-to-many",
                        target="Book",
                        lazy="selectin"  # This will be parsed as LazyStrategy.SELECTIN
                    )
                ]
            ),
            EntitySpec(
                name="Book",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]
            ),
        ]
    )

    state = translate(erd)

    # Get the relationship from the state
    rels = state["relationships"]
    assert len(rels) > 0, "Should have at least one relationship"

    rel = rels[0]

    # Verify cardinality is a string, not an enum instance
    assert isinstance(rel["cardinality"], str), (
        f"cardinality should be string, got {type(rel['cardinality']).__name__}: {repr(rel['cardinality'])}"
    )
    assert rel["cardinality"] == "one-to-many", (
        f"cardinality should be 'one-to-many', got {repr(rel['cardinality'])}"
    )
    assert not rel["cardinality"].startswith("Cardinality."), (
        f"cardinality should not be enum repr: {repr(rel['cardinality'])}"
    )

    # Verify lazy is a string (or None if not set)
    source = rel["source"]
    assert isinstance(source["lazy"], (str, type(None))), (
        f"lazy should be string or None, got {type(source['lazy']).__name__}: {repr(source['lazy'])}"
    )
    assert source["lazy"] == "selectin", (
        f"lazy should be 'selectin', got {repr(source['lazy'])}"
    )
    assert not str(source["lazy"]).startswith("LazyStrategy."), (
        f"lazy should not be enum repr: {repr(source['lazy'])}"
    )


def test_translate_groups_entities_into_modules():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    assert len(state["modules"]) == 1
    module = state["modules"][0]
    assert module["name"] == "catalog"
    assert module["snake_name"] == "catalog"
    entity_names = {e["name"] for e in module["entities"]}
    assert entity_names == {"Category", "Product"}

    # Each module entity is the exact same shape as a crud_entities entry.
    product = next(e for e in module["entities"] if e["name"] == "Product")
    assert product["base_path"] == "/products"
    assert product["rbac"]["create"] == ["admin"]


def test_translate_resolves_default_auth_module_name():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")  # auth enabled, no services: entry for User
    state = translate(erd)
    assert state["auth_module_name"] == "auth"


def test_translate_resolves_renamed_auth_module_name():
    erd = ERDConfig(
        project=ProjectMeta(name="Demo", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="demo.db"),
        auth=AuthSpec(enabled=True),
        entities=[
            EntitySpec(name="Widget", fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]),
        ],
        services=[
            ServiceDecl(name="widgets", entities=["Widget"]),
            ServiceDecl(name="identity", entities=["User"]),
        ],
    )
    state = translate(erd)
    assert state["auth_module_name"] == "identity"
    # The renamed auth service must not also appear in `modules` (it's handled separately).
    assert all(m["name"] != "identity" for m in state["modules"])


def test_translate_multiple_modules_stay_distinct():
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")  # catalog: [Category, Product], ordering: [Order]
    state = translate(erd)

    module_names = {m["name"] for m in state["modules"]}
    assert module_names == {"catalog", "ordering"}

    catalog = next(m for m in state["modules"] if m["name"] == "catalog")
    ordering = next(m for m in state["modules"] if m["name"] == "ordering")
    assert {e["name"] for e in catalog["entities"]} == {"Category", "Product"}
    assert {e["name"] for e in ordering["entities"]} == {"Order"}


def test_translate_auth_user_fields_have_defaults():
    """Regression test: ensure all auth User fields have a 'default' key to prevent Jinja syntax errors.

    When generating database/models.py, Jinja checks {% if field.default is not none %} before
    emitting a default= kwarg. If the key is missing entirely, Jinja's Undefined sentinel is
    not the literal None, so the check passes and Jinja tries to emit "default=<undefined>",
    which becomes a syntax error. All AUTH_USER_FIELDS must have explicit 'default' keys.
    """
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    # Find User model
    user_model = next((m for m in state["data_models"] if m["name"] == "User"), None)
    assert user_model is not None, "User model should be present when auth is enabled"

    # Verify every field has a 'default' key
    for field in user_model["fields"]:
        assert "default" in field, (
            f"User field '{field['name']}' must have 'default' key (even if None) to prevent Jinja syntax errors"
        )

    # Render models.py and verify syntax is valid
    from backend.services.code_generator import CodeGenerator
    import tempfile, ast

    with tempfile.TemporaryDirectory() as tmp:
        gen = CodeGenerator(output_dir=tmp)
        codebase = gen.generate_project(state, force=True)
        models_src = (codebase / 'database' / 'models.py').read_text(encoding='utf-8')

        # Check for the problematic "default=," pattern
        assert 'default=,' not in models_src, "Generated models.py should not contain 'default=,' syntax errors"

        # Parse the file to verify syntax
        try:
            ast.parse(models_src)
        except SyntaxError as e:
            raise AssertionError(f"Generated models.py has syntax error: {e}")
