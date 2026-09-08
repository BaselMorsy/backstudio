from backend.erd.loader import load_erd
from backend.erd.visualize import render_html, render_mermaid

FIXTURES = "backend/tests/fixtures/erd"


def test_render_mermaid_includes_entities_and_relationship():
    erd = load_erd(f"{FIXTURES}/valid_full.yml")
    diagram = render_mermaid(erd)

    assert "erDiagram" in diagram
    assert "Product" in diagram
    assert "Category" in diagram
    assert "User" in diagram  # auto-injected since auth is enabled
    assert "many-to-one" not in diagram  # cardinality rendered as symbols, not the word
    assert "category" in diagram  # relationship label
    # Verify correct FieldType enum mapping: Product has int id and float price fields
    assert "int id" in diagram  # id should map to int, not default to string
    assert "float price" in diagram  # price should map to float, not default to string


def test_render_html_wraps_diagram_and_loads_mermaid():
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    html = render_html(erd)

    assert "<title>Demo - ERD</title>" in html
    assert "mermaid" in html.lower()
    assert "erDiagram" in html
    assert "Widget" in html
