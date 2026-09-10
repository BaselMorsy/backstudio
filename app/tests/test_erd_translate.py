import pytest
from pydantic import ValidationError

from app.erd.loader import load_erd, ERDValidationError
from app.erd.translate import translate
from app.erd.schema import (
    ERDConfig,
    ProjectMeta,
    DatabaseSpec,
    EntitySpec,
    RelationshipDecl,
    EndpointSpec,
    AuthSpec,
    ServiceDecl,
    ModelField,
    FieldType,
)

FIXTURES = "app/tests/fixtures/erd"


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

    from app.services.code_generator import CodeGenerator

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
    from app.erd.loader import ERDValidationError

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
    from app.erd.schema import LazyStrategy

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
    from app.services.code_generator import CodeGenerator
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


def test_owned_relationships_many_to_one():
    """Post declares many-to-one to Category: Post owns the FK, Category doesn't."""
    erd = ERDConfig(
        project=ProjectMeta(name="Blog", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="blog.db"),
        entities=[
            EntitySpec(
                name="Category",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
            EntitySpec(
                name="Post",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="category", cardinality="many-to-one", target="Category")
                ],
            ),
        ],
        services=[ServiceDecl(name="content", entities=["Category", "Post"])],
    )
    state = translate(erd)

    category = next(m for m in state["data_models"] if m["name"] == "Category")
    post = next(m for m in state["data_models"] if m["name"] == "Post")
    assert category["owned_relationships"] == []
    assert post["owned_relationships"] == [
        {
            "attribute": "category",
            "fk_column": "category_id",
            "fk_nullable": True,
            "target_model": "Category",
            "target_snake": "category",
            "owner": False,
            "cascades_ownership": False,
            "is_rls_link": False,
        }
    ]
    assert category["many_to_many_relationships"] == []
    assert post["many_to_many_relationships"] == []

    # crud_entities carry the identical derived lists
    post_entity = next(e for e in state["modules"][0]["entities"] if e["name"] == "Post")
    assert post_entity["owned_relationships"] == post["owned_relationships"]


def test_owned_relationships_one_to_many_equivalent_to_many_to_one():
    """Author declares one-to-many to Book: per translate.py's existing normalization
    the FK lives on Book (the target), so Book - not Author - is the owning side.
    This must produce the identical shape test_owned_relationships_many_to_one gets
    from declaring the relationship the other way around.
    """
    erd = ERDConfig(
        project=ProjectMeta(name="Library", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="library.db"),
        entities=[
            EntitySpec(
                name="Author",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="author_books", cardinality="one-to-many", target="Book")
                ],
            ),
            EntitySpec(
                name="Book",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
        ],
        services=[ServiceDecl(name="library", entities=["Author", "Book"])],
    )
    state = translate(erd)

    author = next(m for m in state["data_models"] if m["name"] == "Author")
    book = next(m for m in state["data_models"] if m["name"] == "Book")
    assert author["owned_relationships"] == []
    assert book["owned_relationships"] == [
        {
            "attribute": "author",
            "fk_column": "author_id",
            "fk_nullable": True,
            "target_model": "Author",
            "target_snake": "author",
            "owner": False,
            "cascades_ownership": False,
            "is_rls_link": False,
        }
    ]


def test_owned_relationships_required_fk_not_nullable():
    erd = ERDConfig(
        project=ProjectMeta(name="Blog", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="blog.db"),
        entities=[
            EntitySpec(
                name="Category",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
            EntitySpec(
                name="Post",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(
                        name="category", cardinality="many-to-one", target="Category", nullable=False
                    )
                ],
            ),
        ],
        services=[ServiceDecl(name="content", entities=["Category", "Post"])],
    )
    state = translate(erd)
    post = next(m for m in state["data_models"] if m["name"] == "Post")
    assert post["owned_relationships"][0]["fk_nullable"] is False


def test_many_to_many_relationships_both_sides():
    erd = ERDConfig(
        project=ProjectMeta(name="Blog", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="blog.db"),
        entities=[
            EntitySpec(
                name="Post",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="tags", cardinality="many-to-many", target="Tag")
                ],
            ),
            EntitySpec(
                name="Tag",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
        ],
        services=[ServiceDecl(name="content", entities=["Post", "Tag"])],
    )
    state = translate(erd)

    post = next(m for m in state["data_models"] if m["name"] == "Post")
    tag = next(m for m in state["data_models"] if m["name"] == "Tag")

    assert post["owned_relationships"] == []
    assert post["many_to_many_relationships"] == [
        {"attribute": "tags", "target_model": "Tag", "target_plural_snake": "tags"}
    ]
    assert tag["many_to_many_relationships"] == [
        {"attribute": "posts", "target_model": "Post", "target_plural_snake": "posts"}
    ]


def test_self_referential_many_to_one_produces_distinct_views_and_single_owned_fk():
    """Employee.manager: both the FK-owning ('manager') and reverse-collection
    ('manager_employees') views live on the SAME entity - must get distinct
    attribute names, and owned_relationships must count the FK exactly once even
    though it appears twice in data_models["Employee"]["relationships"] (once per
    _view, one for each of the two relationship() declarations models.py.jinja
    needs to render on the same class).
    """
    erd = ERDConfig(
        project=ProjectMeta(name="Org", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="org.db"),
        entities=[
            EntitySpec(
                name="Employee",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="manager", cardinality="many-to-one", target="Employee")
                ],
            ),
        ],
        services=[ServiceDecl(name="hr", entities=["Employee"])],
    )
    state = translate(erd)

    employee = next(m for m in state["data_models"] if m["name"] == "Employee")
    rels = employee["relationships"]
    assert len(rels) == 2, "self-referential relationship must appear twice (once per _view)"
    views = {r["_view"] for r in rels}
    assert views == {"source", "target"}

    attributes = {r["source"]["attribute"] if r["_view"] == "source" else r["target"]["attribute"] for r in rels}
    assert attributes == {"manager", "manager_employees"}

    assert employee["owned_relationships"] == [
        {
            "attribute": "manager",
            "fk_column": "manager_id",
            "fk_nullable": True,
            "target_model": "Employee",
            "target_snake": "employee",
            "owner": False,
            "cascades_ownership": False,
            "is_rls_link": False,
        }
    ]
    assert employee["many_to_many_relationships"] == []


def test_self_referential_one_to_one_produces_distinct_attributes():
    """Employee.buddy: the default (non-self-ref) one-to-one formula would give
    both sides the identical attribute 'employee' - self-referential must force
    name_basis to keep them distinct.
    """
    erd = ERDConfig(
        project=ProjectMeta(name="Org", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="org.db"),
        entities=[
            EntitySpec(
                name="Employee",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="buddy", cardinality="one-to-one", target="Employee")
                ],
            ),
        ],
        services=[ServiceDecl(name="hr", entities=["Employee"])],
    )
    state = translate(erd)

    employee = next(m for m in state["data_models"] if m["name"] == "Employee")
    rels = employee["relationships"]
    assert len(rels) == 2

    attributes = {r["source"]["attribute"] if r["_view"] == "source" else r["target"]["attribute"] for r in rels}
    assert attributes == {"buddy", "buddy_employee"}
    assert len(attributes) == 2, "the two self-referential views must not collide on the same attribute name"

    assert employee["owned_relationships"] == [
        {
            "attribute": "buddy",
            "fk_column": "buddy_id",
            "fk_nullable": True,
            "target_model": "Employee",
            "target_snake": "employee",
            "owner": False,
            "cascades_ownership": False,
            "is_rls_link": False,
        }
    ]


def test_self_referential_one_to_many_produces_distinct_attributes():
    """Category.children: the default (non-self-ref) one-to-many target_attribute
    formula (name_basis alone, no suffix) would collide with source_attribute
    (also name_basis) once both land on the same class - needs its own
    self-referential suffix, distinct from one-to-one's/many-to-one's.
    """
    erd = ERDConfig(
        project=ProjectMeta(name="Catalog", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="catalog.db"),
        entities=[
            EntitySpec(
                name="Category",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[
                    RelationshipDecl(name="children", cardinality="one-to-many", target="Category")
                ],
            ),
        ],
        services=[ServiceDecl(name="catalog", entities=["Category"])],
    )
    state = translate(erd)

    category = next(m for m in state["data_models"] if m["name"] == "Category")
    rels = category["relationships"]
    assert len(rels) == 2

    attributes = {r["source"]["attribute"] if r["_view"] == "source" else r["target"]["attribute"] for r in rels}
    assert attributes == {"children", "children_category"}
    assert len(attributes) == 2

    # For one-to-many, the target side owns the FK (translate.py's existing
    # normalization) - self-referential or not, that doesn't change.
    assert category["owned_relationships"] == [
        {
            "attribute": "children_category",
            "fk_column": "children_id",
            "fk_nullable": True,
            "target_model": "Category",
            "target_snake": "category",
            "owner": False,
            "cascades_ownership": False,
            "is_rls_link": False,
        }
    ]


def test_translate_passes_database_async_mode_through():
    erd = ERDConfig(
        project=ProjectMeta(name="Demo", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="d.db", async_mode=True),
        entities=[
            EntitySpec(
                name="Widget",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
        ],
        services=[ServiceDecl(name="widgets", entities=["Widget"])],
    )
    state = translate(erd)
    assert state["database_config"]["async_mode"] is True


def test_translate_database_async_mode_defaults_false():
    erd = ERDConfig(
        project=ProjectMeta(name="Demo", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="d.db"),
        entities=[
            EntitySpec(
                name="Widget",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            ),
        ],
        services=[ServiceDecl(name="widgets", entities=["Widget"])],
    )
    state = translate(erd)
    assert state["database_config"]["async_mode"] is False


def test_translate_resolves_root_owned_entity():
    erd = load_erd(f"{FIXTURES}/rls_root_owned.yml")
    state = translate(erd)

    order = next(m for m in state["data_models"] if m["name"] == "Order")
    assert order["rls"] == {
        "is_root": True,
        "root_model": "Order",
        "owner_fk_column": "user_id",
        "join_chain": [],
        "identity_source": {"type": "auth_user", "header_name": None},
        "bypass_roles": ["admin"],
        "read_scope": "owner",
    }

    user_rel = next(r for r in order["owned_relationships"] if r["fk_column"] == "user_id")
    assert user_rel["is_rls_link"] is True

    module_order = next(e for m in state["modules"] for e in m["entities"] if e["name"] == "Order")
    assert module_order["rls"] == order["rls"]
    module_user_rel = next(r for r in module_order["owned_relationships"] if r["fk_column"] == "user_id")
    assert module_user_rel["is_rls_link"] is True


def test_translate_resolves_read_scope_any_authenticated_on_root_owned_entity():
    """RLSSpec.read_scope defaults to 'owner' (already covered above); this confirms an
    entity that explicitly sets read_scope: any_authenticated has that value threaded
    through into its resolved rls dict, and that a sibling entity in the same ERD that
    leaves it unset still resolves to the 'owner' default - the default is genuinely
    per-entity, not globally flipped by another entity opting in.
    """
    erd = load_erd(f"{FIXTURES}/rls_read_scope_any_authenticated.yml")
    state = translate(erd)

    note = next(m for m in state["data_models"] if m["name"] == "Note")
    assert note["rls"]["read_scope"] == "any_authenticated"

    secret = next(m for m in state["data_models"] if m["name"] == "Secret")
    assert secret["rls"]["read_scope"] == "owner"

    announcement = next(m for m in state["data_models"] if m["name"] == "Announcement")
    assert announcement["rls"]["read_scope"] == "any_authenticated"
    assert announcement["rls"]["identity_source"]["type"] == "header"


def test_translate_resolves_one_hop_cascade():
    erd = load_erd(f"{FIXTURES}/rls_cascade_owned.yml")
    state = translate(erd)

    order_item = next(m for m in state["data_models"] if m["name"] == "OrderItem")
    assert order_item["rls"]["is_root"] is False
    assert order_item["rls"]["root_model"] == "Order"
    assert order_item["rls"]["owner_fk_column"] == "user_id"
    assert order_item["rls"]["join_chain"] == [
        {"from_model": "OrderItem", "from_fk_column": "order_id", "to_model": "Order", "to_pk_column": "id"}
    ]
    assert order_item["rls"]["identity_source"] == {"type": "auth_user", "header_name": None}
    assert order_item["rls"]["bypass_roles"] == []
    # A cascade-owned entity's rls dict is a full copy propagated from its root - it has no
    # rls: block of its own to read read_scope from, so this must come from the root too.
    assert order_item["rls"]["read_scope"] == "owner"

    order_rel = next(r for r in order_item["owned_relationships"] if r["fk_column"] == "order_id")
    assert order_rel["is_rls_link"] is True


def test_translate_resolves_two_hop_cascade():
    erd = load_erd(f"{FIXTURES}/rls_cascade_owned.yml")
    state = translate(erd)

    discount = next(m for m in state["data_models"] if m["name"] == "OrderLineDiscount")
    assert discount["rls"]["is_root"] is False
    assert discount["rls"]["root_model"] == "Order"
    assert discount["rls"]["owner_fk_column"] == "user_id"
    assert discount["rls"]["join_chain"] == [
        {
            "from_model": "OrderLineDiscount",
            "from_fk_column": "order_item_id",
            "to_model": "OrderItem",
            "to_pk_column": "id",
        },
        {"from_model": "OrderItem", "from_fk_column": "order_id", "to_model": "Order", "to_pk_column": "id"},
    ]


def test_translate_unrelated_entity_has_no_rls():
    erd = load_erd(f"{FIXTURES}/rls_cascade_owned.yml")
    state = translate(erd)

    category = next(m for m in state["data_models"] if m["name"] == "Category")
    assert category["rls"] is None
    assert category["owned_relationships"] == []  # Category owns no FKs at all in this fixture


def test_translate_entity_with_owned_relationships_but_no_rls_is_unaffected():
    """An entity that has an ordinary owned_relationship (FK) but neither owner:true nor
    cascades_ownership:true anywhere must come out with rls: None and every one of its
    owned_relationships entries' is_rls_link False - RLS involvement is opt-in per entity,
    not inferred from having FKs at all.
    """
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    state = translate(erd)

    product = next(m for m in state["data_models"] if m["name"] == "Product")
    assert product["rls"] is None
    assert len(product["owned_relationships"]) == 1
    assert product["owned_relationships"][0]["is_rls_link"] is False


def test_cascades_ownership_cycle_rejected():
    erd = ERDConfig(
        project=ProjectMeta(name="Cyclic", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="c.db"),
        entities=[
            EntitySpec(
                name="A",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[RelationshipDecl(name="b", cardinality="many-to-one", target="B", cascades_ownership=True)],
            ),
            EntitySpec(
                name="B",
                fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
                relationships=[RelationshipDecl(name="a", cardinality="many-to-one", target="A", cascades_ownership=True)],
            ),
        ],
        services=[ServiceDecl(name="ab", entities=["A", "B"])],
    )
    with pytest.raises(ERDValidationError, match="cycle"):
        translate(erd)


def test_ambiguous_multi_path_is_structurally_impossible_at_schema_level():
    """Documents the Global Constraints/Task 3 design note: Task 1's at-most-one-
    cascades_ownership-relationship-per-entity rule already makes a genuine multi-path
    ambiguity unconstructable - this fails at EntitySpec construction, never reaching
    translate() at all.
    """
    with pytest.raises(ValidationError):
        EntitySpec(
            name="OrderItem",
            fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)],
            relationships=[
                RelationshipDecl(name="order", cardinality="many-to-one", target="Order", cascades_ownership=True),
                RelationshipDecl(name="batch", cardinality="many-to-one", target="Batch", cascades_ownership=True),
            ],
        )


def test_translate_email_verification_mode_adds_is_verified_field():
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    user = next(m for m in state["data_models"] if m["name"] == "User")
    field_names = [f["name"] for f in user["fields"]]
    assert "is_verified" in field_names
    assert "is_approved" not in field_names

    is_verified_field = next(f for f in user["fields"] if f["name"] == "is_verified")
    assert is_verified_field["type"] == "boolean"
    assert is_verified_field["nullable"] is False
    assert is_verified_field["default"] is False

    assert state["registration_mode"] == "email_verification"


def test_translate_admin_approval_mode_adds_is_approved_field():
    erd = load_erd(f"{FIXTURES}/auth_admin_approval.yml")
    state = translate(erd)

    user = next(m for m in state["data_models"] if m["name"] == "User")
    field_names = [f["name"] for f in user["fields"]]
    assert "is_approved" in field_names
    assert "is_verified" not in field_names

    is_approved_field = next(f for f in user["fields"] if f["name"] == "is_approved")
    assert is_approved_field["type"] == "boolean"
    assert is_approved_field["nullable"] is False
    assert is_approved_field["default"] is False

    assert state["registration_mode"] == "admin_approval"


def test_translate_open_mode_adds_neither_field():
    erd = load_erd(f"{FIXTURES}/shophub_mini.yml")
    state = translate(erd)

    user = next(m for m in state["data_models"] if m["name"] == "User")
    field_names = [f["name"] for f in user["fields"]]
    assert "is_verified" not in field_names
    assert "is_approved" not in field_names
    assert state["registration_mode"] == "open"


def test_translate_threads_jwt_lifetimes_into_security_config():
    erd = load_erd(f"{FIXTURES}/auth_email_verification.yml")
    state = translate(erd)

    sec = state["security_config"]
    assert sec["jwt_expiration_minutes"] == 30
    assert sec["jwt_refresh_expiration_minutes"] == 10080
    assert sec["jwt_email_verification_expiration_minutes"] == 1440
    assert sec["jwt_password_reset_expiration_minutes"] == 30


def test_translate_custom_jwt_lifetimes_flow_through():
    from app.erd.schema import ERDConfig, ProjectMeta, DatabaseSpec, AuthSpec, JWTSpec, EntitySpec, ServiceDecl, ModelField, FieldType

    erd = ERDConfig(
        project=ProjectMeta(name="CustomLifetimes", version="1.0.0"),
        database=DatabaseSpec(type="sqlite", database_name="c.db"),
        auth=AuthSpec(
            enabled=True,
            jwt=JWTSpec(
                refresh_token_expiration_minutes=5,
                email_verification_expiration_minutes=7,
                password_reset_expiration_minutes=1,
            ),
        ),
        entities=[
            EntitySpec(name="Widget", fields=[ModelField(name="id", type=FieldType.INTEGER, primary_key=True)]),
        ],
        services=[ServiceDecl(name="widgets", entities=["Widget"])],
    )
    state = translate(erd)

    sec = state["security_config"]
    assert sec["jwt_refresh_expiration_minutes"] == 5
    assert sec["jwt_email_verification_expiration_minutes"] == 7
    assert sec["jwt_password_reset_expiration_minutes"] == 1
