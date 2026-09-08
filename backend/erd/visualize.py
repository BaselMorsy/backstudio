"""Render a standalone HTML page with a Mermaid ER diagram for an ERDConfig."""

from html import escape
from typing import List

from backend.erd.schema import ERDConfig
from backend.schemas.data import ModelField

_MERMAID_TYPE_MAP = {
    "string": "string", "integer": "int", "float": "float", "boolean": "bool",
    "datetime": "datetime", "date": "date", "text": "text", "json": "json", "uuid": "uuid",
}

_CARDINALITY_SYMBOLS = {
    "one-to-many": ("||", "o{"),
    "many-to-one": ("}o", "||"),
    "one-to-one": ("||", "||"),
    "many-to-many": ("}o", "o{"),
}

_AUTH_USER_DISPLAY_FIELDS: List[ModelField] = [
    ModelField(name="id", type="integer", primary_key=True),
    ModelField(name="email", type="string", unique=True),
    ModelField(name="roles", type="json"),
]


def _entity_block(name: str, fields: List[ModelField]) -> str:
    lines = [f"    {name} {{"]
    for field in fields:
        mtype = _MERMAID_TYPE_MAP.get(field.type.value, "string")
        markers = []
        if field.primary_key:
            markers.append("PK")
        if field.unique and not field.primary_key:
            markers.append("UK")
        marker = " " + ",".join(markers) if markers else ""
        lines.append(f"        {mtype} {field.name}{marker}")
    lines.append("    }")
    return "\n".join(lines)


def render_mermaid(erd: ERDConfig) -> str:
    lines = ["erDiagram"]
    for entity in erd.entities:
        lines.append(_entity_block(entity.name, entity.fields))

    if erd.auth.enabled:
        lines.append(_entity_block("User", _AUTH_USER_DISPLAY_FIELDS))

    for entity in erd.entities:
        for rel in entity.relationships:
            left, right = _CARDINALITY_SYMBOLS[rel.cardinality.value]
            lines.append(f'    {entity.name} {left}--{right} {rel.target} : "{rel.name}"')

    return "\n".join(lines)


def render_html(erd: ERDConfig) -> str:
    diagram = render_mermaid(erd)
    title = escape(erd.project.name)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title} - ERD</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body {{ font-family: sans-serif; margin: 2rem; background: #fafafa; }}
  h1 {{ font-size: 1.25rem; }}
  .mermaid {{ background: white; padding: 1rem; border-radius: 8px; }}
</style>
</head>
<body>
<h1>{title} &mdash; Entity Relationship Diagram</h1>
<pre class="mermaid">
{escape(diagram)}
</pre>
<script>mermaid.initialize({{ startOnLoad: true }});</script>
</body>
</html>
"""
