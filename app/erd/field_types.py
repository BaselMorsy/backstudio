"""Single source of truth for how each ERD field type maps to generated code.

CodeGenerator (Jinja globals/filters) and visualize.py both read from here, so a field type
is defined once instead of in four parallel dictionaries. This module deliberately imports
nothing from the rest of `app`, so schema.py, loader.py, translate.py and the generator can
all import it without cycles.
"""

from typing import Any

_SA_TYPE = {
    "string": "String",
    "integer": "Integer",
    "float": "Float",
    "boolean": "Boolean",
    "datetime": "DateTime",
    "date": "Date",
    "text": "Text",
    "json": "JSON",
    "uuid": "String",
}

_PY_TYPE = {
    "string": "str", "integer": "int", "float": "float", "boolean": "bool",
    "datetime": "datetime", "date": "date", "text": "str", "json": "Any", "uuid": "str",
}

_MERMAID_TYPE = {
    "string": "string", "integer": "int", "float": "float", "boolean": "bool",
    "datetime": "datetime", "date": "date", "text": "text", "json": "json", "uuid": "uuid",
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
