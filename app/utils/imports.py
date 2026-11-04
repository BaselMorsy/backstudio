"""Drop unused top-level imports from generated Python source."""

import ast
import re

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ANNOTATION_LIKE = re.compile(r"[A-Za-z_][\w.\[\], |]*")


def _bound_name(alias: ast.alias) -> str:
    return alias.asname or alias.name.split(".")[0]


def _render(node: ast.stmt, kept: list[ast.alias]) -> str:
    names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in kept)
    if isinstance(node, ast.Import):
        return f"import {names}"
    assert isinstance(node, ast.ImportFrom)
    return f"from {'.' * node.level}{node.module or ''} import {names}"


def prune_unused_imports(source: str) -> str:
    """Remove module-level imports whose names are never used.

    Templates emit a fixed import header that each project only partly needs. Names inside annotation-like
    string constants are kept, so forward references and ``__all__`` entries survive; prose in
    docstrings does not count as a use.
    Imports marked ``noqa`` are left alone. Source that does not parse is returned unchanged.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _ANNOTATION_LIKE.fullmatch(node.value):
            used.update(_WORD.findall(node.value))

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        if any(a.name == "*" for a in node.names):
            continue
        if "noqa" in "".join(lines[node.lineno - 1 : node.end_lineno]):
            continue  # kept on purpose, e.g. imported only for its side effects
        kept = [a for a in node.names if _bound_name(a) in used]
        if len(kept) == len(node.names):
            continue
        assert node.end_lineno is not None
        indent = " " * node.col_offset
        replacement = f"{indent}{_render(node, kept)}\n" if kept else ""
        edits.append((node.lineno - 1, node.end_lineno, replacement))

    if not edits:
        return source
    for start, end, replacement in reversed(edits):
        lines[start:end] = [replacement] if replacement else []
    return re.sub(r"\n{4,}", "\n\n\n", "".join(lines))
