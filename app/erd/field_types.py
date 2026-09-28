"""Single source of truth for how each ERD field type maps to generated code.

CodeGenerator (Jinja globals/filters) and visualize.py both read from here, so a field type
is defined once instead of in four parallel dictionaries. This module deliberately imports
nothing from the rest of `app`, so schema.py, loader.py, translate.py and the generator can
all import it without cycles.
"""

import enum
import keyword
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping

_SA_TYPE = {
    "string": "String",
    "integer": "Integer",
    "bigint": "BigInteger",
    "float": "Float",
    "decimal": "Numeric",
    "boolean": "Boolean",
    "datetime": "DateTime",
    "date": "Date",
    "text": "Text",
    "json": "JSON",
    "uuid": "Uuid(as_uuid=True)",
    "enum": "Enum",
}

_PY_TYPE = {
    "string": "str", "integer": "int", "bigint": "int", "float": "float", "decimal": "Decimal",
    "boolean": "bool", "datetime": "datetime", "date": "date", "text": "str", "json": "Any",
    "uuid": "UUID",
}

_MERMAID_TYPE = {
    "string": "string", "integer": "int", "bigint": "bigint", "float": "float",
    "decimal": "decimal", "boolean": "bool", "datetime": "datetime", "date": "date",
    "text": "text", "json": "json", "uuid": "uuid", "enum": "enum",
}


def type_value(field_type: Any) -> str:
    """Plain lower-case string for a FieldType member (whose str() is 'FieldType.X') or a str."""
    return str(getattr(field_type, "value", field_type)).lower()


def sa_type_for(field_type: Any) -> str:
    return _SA_TYPE.get(type_value(field_type), "String")


def py_type_for(field_type: Any) -> str:
    return _PY_TYPE.get(type_value(field_type), "str")


def mermaid_type(field_type: Any) -> str:
    return _MERMAID_TYPE.get(type_value(field_type), "string")


def python_literal(value: Any) -> str:
    """Render a Python value as source (the Jinja `python_value` filter)."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return repr(value)
    if value is None:
        return "None"
    return str(value)


def pascal_case(text: str) -> str:
    """Must stay identical to `to_pascal_case` in app/services/code_generator.py (the Jinja
    `pascal_case` filter): enum class names are built here but referenced from templates that
    use the filter for model class names, so drift would make them disagree."""
    if text and text[0].isupper() and any(c.isupper() for c in text[1:]):
        return text
    return "".join(word.capitalize() for word in text.replace("_", " ").split())


ENUM_MEMBER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def is_safe_enum_member(value: Any) -> bool:
    """True when `value` can be a generated `class X(str, Enum)` member name AND used verbatim
    as the stored value: no keywords (class, None, True), nothing that shadows or collides with
    a str/Enum attribute (name, value, mro, count, upper, ...), no leading underscore."""
    return (
        isinstance(value, str)
        and bool(ENUM_MEMBER_RE.match(value))
        and not keyword.iskeyword(value)
        and not hasattr(str, value)
        and not hasattr(enum.Enum, value)  # metaclass attributes such as `mro`
        and value not in vars(enum.Enum)  # `name`/`value` are class-hidden DynamicClassAttributes: hasattr() and dir() miss them
    )


def to_decimal(value: Any) -> Decimal:
    """Parse a YAML default as an exact Decimal via its string form (0.1 -> Decimal('0.1'),
    never the float's binary expansion). Rejects bools, non-numbers and NaN/Infinity."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{value!r} is not a number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{value!r} is not a valid decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{value!r} is not a finite decimal")
    return result


def enum_class_name(entity_name: str, field_name: str) -> str:
    return pascal_case(entity_name) + pascal_case(field_name)


def _is(field: Mapping[str, Any], name: str) -> bool:
    return type_value(field.get("type")) == name


def sa_column_type(field: Mapping[str, Any], with_length: bool = True) -> str:
    """Full SQLAlchemy column-type expression for a field dict from the translate state.
    `with_length=False` is used for primary-key lines, which never rendered String(n)."""
    if _is(field, "string"):
        max_length = field.get("max_length")
        return f"String({max_length})" if with_length and max_length else "String"
    if _is(field, "decimal"):
        return f"Numeric({field['precision']}, {field['scale']})"
    if _is(field, "datetime"):
        return "DateTime" if field.get("timezone") is False else "DateTime(timezone=True)"
    if _is(field, "bigint") and field.get("primary_key"):
        # SQLite only autoincrements a plain INTEGER PRIMARY KEY.
        return 'BigInteger().with_variant(Integer(), "sqlite")'
    if _is(field, "enum"):
        return (
            f"Enum({field['enum_class']}, native_enum=False, create_constraint=True, "
            f"name={field['enum_constraint']!r})"
        )
    return sa_type_for(field.get("type"))


def py_type(field: Mapping[str, Any]) -> str:
    if _is(field, "enum"):
        return field["enum_class"]
    return py_type_for(field.get("type"))


def py_default(field: Mapping[str, Any]) -> str:
    """Python source for a field's default (caller only asks when a default exists)."""
    value = field.get("default")
    if _is(field, "decimal"):
        return f"Decimal({str(to_decimal(value))!r})"
    if _is(field, "enum"):
        return f"{field['enum_class']}.{value}"
    return python_literal(value)


_EXTRA_IMPORT_FOR_TYPE = {"bigint": "BigInteger", "decimal": "Numeric", "uuid": "Uuid", "enum": "Enum"}
_EXTRA_IMPORT_ORDER = ("BigInteger", "Enum", "Numeric", "Uuid")


def sa_extra_imports(project: Mapping[str, Any]) -> List[str]:
    """SQLAlchemy names models.py needs beyond its fixed base import list, in a stable order."""
    needed = set()

    def note(type_name: Any) -> None:
        name = _EXTRA_IMPORT_FOR_TYPE.get(type_value(type_name))
        if name:
            needed.add(name)

    for model in project.get("data_models", []):
        for field in model.get("fields", []):
            note(field.get("type"))
    for rel in project.get("relationships", []):
        fk = rel.get("foreign_key")
        if fk:
            note(fk.get("column_type"))
        assoc = rel.get("association_table")
        if assoc:
            note(assoc["left_foreign_key"].get("column_type"))
            note(assoc["right_foreign_key"].get("column_type"))
    return [name for name in _EXTRA_IMPORT_ORDER if name in needed]


def schema_type_imports(fields: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Which extra imports a module's schemas.py needs for the given field dicts."""
    fields = list(fields)
    types = {type_value(f.get("type")) for f in fields}
    return {
        "decimal": "decimal" in types,
        "uuid": "uuid" in types,
        "enums": sorted({f["enum_class"] for f in fields if type_value(f.get("type")) == "enum"}),
    }
