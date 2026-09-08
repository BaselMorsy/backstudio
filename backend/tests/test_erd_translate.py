from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.erd.schema import ERDConfig, ProjectMeta, DatabaseSpec, EntitySpec, RelationshipDecl, EndpointSpec
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

    # Check crud_entities fields as well
    product_entity = next(e for e in state["crud_entities"] if e["name"] == "Product")
    for field in product_entity["fields"]:
        assert isinstance(field["type"], str), (
            f"CRUD entity field {field['name']} type should be string, got {type(field['type']).__name__}"
        )
