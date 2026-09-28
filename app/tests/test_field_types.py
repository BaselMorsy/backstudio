import pytest

from app.erd import field_types as ft
from app.erd.schema import FieldType
from app.services.code_generator import CodeGenerator

LEGACY_SA = {
    "string": "String", "integer": "Integer", "float": "Float", "boolean": "Boolean",
    "datetime": "DateTime", "date": "Date", "text": "Text", "json": "JSON", "uuid": "Uuid(as_uuid=True)",
}
LEGACY_PY = {
    "string": "str", "integer": "int", "float": "float", "boolean": "bool",
    "datetime": "datetime", "date": "date", "text": "str", "json": "Any", "uuid": "UUID",
}
LEGACY_MERMAID = {
    "string": "string", "integer": "int", "float": "float", "boolean": "bool",
    "datetime": "datetime", "date": "date", "text": "text", "json": "json", "uuid": "uuid",
}


@pytest.mark.parametrize("type_value", sorted(LEGACY_SA))
def test_simple_type_maps_match_the_legacy_maps(type_value):
    assert ft.sa_type_for(type_value) == LEGACY_SA[type_value]
    assert ft.py_type_for(type_value) == LEGACY_PY[type_value]
    assert ft.mermaid_type(type_value) == LEGACY_MERMAID[type_value]
    member = FieldType(type_value)
    assert ft.sa_type_for(member) == LEGACY_SA[type_value]
    assert ft.py_type_for(member) == LEGACY_PY[type_value]
    assert ft.mermaid_type(member) == LEGACY_MERMAID[type_value]


def test_unknown_types_fall_back_like_the_legacy_maps():
    assert ft.sa_type_for("nonsense") == "String"
    assert ft.py_type_for("nonsense") == "str"
    assert ft.mermaid_type("nonsense") == "string"


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, "True"), (False, "False"), (None, "None"), (3, "3"), (2.5, "2.5"),
        ([], "[]"), ("plain", "'plain'"), ("O'Brien's", '"O\'Brien\'s"'),
    ],
)
def test_python_literal_matches_the_old_python_value_filter(value, expected):
    assert ft.python_literal(value) == expected


@pytest.mark.parametrize(
    "text", ["Order", "order_item", "orderItem", "AuditLog", "audit_log", "x", "", "HTTPServer", "my_2nd_thing"]
)
def test_pascal_case_matches_the_codegen_filter(text, tmp_path):
    """Enum class names are built by field_types.pascal_case but referenced from templates
    that use the Jinja `pascal_case` filter for model class names; the two must not drift."""
    generator = CodeGenerator(output_dir=str(tmp_path))
    assert ft.pascal_case(text) == generator.jinja_env.filters["pascal_case"](text)


def test_code_generator_delegates_to_the_registry(tmp_path):
    generator = CodeGenerator(output_dir=str(tmp_path))
    assert generator.jinja_env.filters["python_value"] is ft.python_literal
    assert generator._get_sqlalchemy_type("integer") == "Integer"
    assert generator._get_python_type("json") == "Any"
    assert generator._get_python_type(FieldType.FLOAT) == "float"


from decimal import Decimal


def _field(type_, **extra):
    return {"name": "f", "type": type_, "nullable": True, "default": None, **extra}


@pytest.mark.parametrize(
    "value,ok",
    [
        ("ACTIVE", True), ("in_progress", True), ("A1", True), ("Posted", True),
        ("class", False), ("None", False), ("True", False), ("mro", False), ("name", False),
        ("value", False), ("count", False), ("upper", False), ("_x", False), ("__x", False),
        ("1A", False), ("in-progress", False), ("has space", False), ("", False),
    ],
)
def test_is_safe_enum_member(value, ok):
    assert ft.is_safe_enum_member(value) is ok


@pytest.mark.parametrize(
    "value,expected",
    [(0.1, "0.1"), (0, "0"), ("12.50", "12.50"), (5, "5"), ("1e-7", "1E-7")],
)
def test_to_decimal_uses_the_decimal_string_not_the_float_bits(value, expected):
    assert ft.to_decimal(value) == Decimal(expected)
    assert str(ft.to_decimal(value)) == str(Decimal(expected))


@pytest.mark.parametrize("bad", [True, False, "abc", "NaN", "Infinity", None, [1], {"a": 1}])
def test_to_decimal_rejects_non_numbers_bools_and_non_finite(bad):
    with pytest.raises(ValueError):
        ft.to_decimal(bad)


def test_enum_class_name():
    assert ft.enum_class_name("Order", "status") == "OrderStatus"
    assert ft.enum_class_name("audit_log", "item_status") == "AuditLogItemStatus"


def test_sa_column_type_variants():
    assert ft.sa_column_type(_field("string")) == "String"
    assert ft.sa_column_type(_field("string", max_length=200)) == "String(200)"
    assert ft.sa_column_type(_field("string", max_length=200), with_length=False) == "String"
    assert ft.sa_column_type(_field("text", max_length=200)) == "Text"
    assert ft.sa_column_type(_field("integer", primary_key=True)) == "Integer"
    assert ft.sa_column_type(_field("bigint")) == "BigInteger"
    assert ft.sa_column_type(_field("bigint", primary_key=True)) == 'BigInteger().with_variant(Integer(), "sqlite")'
    assert ft.sa_column_type(_field("decimal", precision=18, scale=2)) == "Numeric(18, 2)"
    assert ft.sa_column_type(_field("uuid")) == "Uuid(as_uuid=True)"
    assert ft.sa_column_type(_field("datetime")) == "DateTime(timezone=True)"
    assert ft.sa_column_type(_field("datetime", timezone=True)) == "DateTime(timezone=True)"
    assert ft.sa_column_type(_field("datetime", timezone=False)) == "DateTime"
    assert ft.sa_column_type(_field("date")) == "Date"
    assert (
        ft.sa_column_type(_field("enum", enum_class="WidgetStatus", enum_constraint="ck_widgets_status"))
        == "Enum(WidgetStatus, native_enum=False, create_constraint=True, name='ck_widgets_status')"
    )


def test_py_type_variants():
    assert ft.py_type(_field("bigint")) == "int"
    assert ft.py_type(_field("decimal", precision=5, scale=2)) == "Decimal"
    assert ft.py_type(_field("uuid")) == "UUID"
    assert ft.py_type(_field("enum", enum_class="WidgetStatus")) == "WidgetStatus"
    assert ft.py_type(_field("json")) == "Any"
    assert ft.py_type(_field("nonsense")) == "str"


def test_py_default_variants():
    assert ft.py_default(_field("string", default="O'Brien's")) == '"O\'Brien\'s"'
    assert ft.py_default(_field("integer", default=3)) == "3"
    assert ft.py_default(_field("boolean", default=False)) == "False"
    assert ft.py_default(_field("decimal", precision=10, scale=4, default=0.5)) == "Decimal('0.5')"
    assert ft.py_default(_field("decimal", precision=10, scale=4, default=0)) == "Decimal('0')"
    assert ft.py_default(_field("decimal", precision=10, scale=4, default="12.50")) == "Decimal('12.50')"
    assert ft.py_default(_field("enum", enum_class="WidgetStatus", default="ACTIVE")) == "WidgetStatus.ACTIVE"


def test_sa_extra_imports_orders_and_dedupes():
    project = {
        "data_models": [
            {"fields": [_field("bigint"), _field("uuid"), _field("string")]},
            {"fields": [_field("decimal", precision=5, scale=2), _field("enum", enum_class="X")]},
        ],
        "relationships": [
            {"foreign_key": {"column_type": "bigint"}},
            {"association_table": {"left_foreign_key": {"column_type": "integer"}, "right_foreign_key": {"column_type": "bigint"}}},
        ],
    }
    assert ft.sa_extra_imports(project) == ["BigInteger", "Enum", "Numeric", "Uuid"]
    assert ft.sa_extra_imports({"data_models": [{"fields": [_field("integer")]}], "relationships": []}) == []
    # an FK-only bigint (no bigint field) still needs the import
    assert ft.sa_extra_imports(
        {"data_models": [], "relationships": [{"foreign_key": {"column_type": "bigint"}}]}
    ) == ["BigInteger"]


def test_schema_type_imports():
    fields = [_field("decimal", precision=5, scale=2), _field("enum", enum_class="B"), _field("enum", enum_class="A")]
    assert ft.schema_type_imports(fields) == {"decimal": True, "uuid": False, "enums": ["A", "B"]}
    assert ft.schema_type_imports([_field("string")]) == {"decimal": False, "uuid": False, "enums": []}
