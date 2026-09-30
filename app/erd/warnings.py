"""Non-fatal ERD warnings shown by `backstudio validate` and `backstudio generate`."""

from collections import Counter
from typing import List

from app.erd.schema import ERDConfig
from app.erd.translate import _build_relationship


def _relationship_name_warnings(erd: ERDConfig) -> List[str]:
    """Warn when a relationship's declared `name` will not be used.

    translate() derives attribute/FK names from the *target* unless an entity has two or
    more relationships to the same target (or the relationship is self-referential), in which
    case the declared name is used. Building the relationship both ways and comparing shows
    exactly what the name would have changed; explicit `attribute` / `foreign_key_column`
    make both builds equal, so they silence the warning for what they cover. The FK column is
    only compared for many-to-one / one-to-one: for one-to-many the FK lives on the target and
    is derived from *this* entity's name, so the relationship name was never meant to drive it.
    """
    warnings: List[str] = []
    for entity in erd.entities:
        if entity.name == "User":  # translate() ignores a declared User's relationships
            continue
        target_counts = Counter(rel.target for rel in entity.relationships)
        for rel in entity.relationships:
            if target_counts[rel.target] > 1 or rel.target == entity.name:
                continue
            derived = _build_relationship(erd, entity, rel, False)
            named = _build_relationship(erd, entity, rel, True)
            ignored: List[str] = []
            if derived["source"]["attribute"] != named["source"]["attribute"]:
                ignored.append(f"the attribute is '{derived['source']['attribute']}'")
            if rel.cardinality.value in ("many-to-one", "one-to-one"):
                if derived["foreign_key"]["column"] != named["foreign_key"]["column"]:
                    ignored.append(f"the foreign key column is '{derived['foreign_key']['column']}'")
            if ignored:
                warnings.append(
                    f"{entity.name}.{rel.name} -> {rel.target}: declared name '{rel.name}' is not used; "
                    f"{' and '.join(ignored)} (derived from the target). Set 'attribute:' / "
                    "'foreign_key_column:' to choose them, or declare two relationships to the same target."
                )
    return warnings


def _external_auth_warnings(erd: ERDConfig) -> List[str]:
    """Warn when auth.mode: external omits audience - a token valid for a *different*
    service behind the same issuer would also be accepted here without it."""
    if erd.auth.mode == "external" and erd.auth.external is not None and erd.auth.external.audience is None:
        return [
            "auth.external.audience is not set - any token issued by "
            f"'{erd.auth.external.issuer}' for a *different* service would also be accepted "
            "here. Set audience to this service's expected value unless you're certain no "
            "other service shares this issuer."
        ]
    return []


def collect_warnings(erd: ERDConfig) -> List[str]:
    return _relationship_name_warnings(erd) + _external_auth_warnings(erd)
