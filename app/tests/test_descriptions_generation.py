import ast
import subprocess
import sys

from app.erd.loader import load_erd
from app.erd.translate import translate
from app.erd.visualize import render_mermaid
from app.services.code_generator import CodeGenerator
from app.tests.test_generated_project_runtime import _GeneratedProjectImporter, isolated_sys_path  # noqa: F401

FIXTURES = "app/tests/fixtures/erd"
FIXTURE = f"{FIXTURES}/descriptions_stress.yml"

ENTITY_DESC = "Prepaid wallet: \"quoted\", 'single', back\\slash, <b>tag</b> & ampersand \U0001F4B0\nsecond line"
PK_DESC = 'Primary key "id" \\ path'
BALANCE_DESC = "Balance in major units - wallet \U0001F4B0, it's \"exact\"\nsecond line"
LABEL_DESC = "Plain label"


def _generate(tmp_path):
    state = translate(load_erd(FIXTURE))
    return CodeGenerator(output_dir=str(tmp_path / "workspace")).generate_project(state, force=True)


def test_descriptions_round_trip_exactly_through_generated_sql_comments(tmp_path):
    codebase_dir = _generate(tmp_path)
    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    tree = ast.parse(models_src)

    comments = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "comment":
                    comments.add(ast.literal_eval(kw.value))
    assert comments == {ENTITY_DESC, PK_DESC, BALANCE_DESC, LABEL_DESC}   # `plain` has none

    wallet = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Wallet")
    assert ast.get_docstring(wallet) == "Wallet model"   # free text never reaches a docstring

    result = subprocess.run([sys.executable, "-m", "compileall", "-q", str(codebase_dir)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_descriptions_reach_pydantic_fields_openapi_and_postgres_comment_ddl(tmp_path, monkeypatch, isolated_sys_path):
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'desc.db').as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        schemas = importlib.import_module("modules.money.schemas")
        assert schemas.WalletCreate.model_fields["balance"].description == BALANCE_DESC
        assert schemas.WalletCreate.model_fields["label"].description == LABEL_DESC
        assert schemas.WalletCreate.model_fields["plain"].description is None
        assert schemas.WalletUpdate.model_fields["label"].description == LABEL_DESC
        assert schemas.WalletResponse.model_fields["id"].description == PK_DESC
        assert schemas.WalletResponse.model_fields["balance"].description == BALANCE_DESC

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            spec = client.get("/openapi.json").json()
            assert spec["components"]["schemas"]["WalletResponse"]["properties"]["label"]["description"] == LABEL_DESC
            created = client.post("/wallets", json={"balance": "5.00", "label": "x"})
            assert created.status_code == 201, created.text

        base = importlib.import_module("database.base")
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import SetColumnComment, SetTableComment

        wallets = {t.name: t for t in base.Base.metadata.sorted_tables}["wallets"]
        # PostgreSQL emits comments as separate statements, not inside CREATE TABLE.
        assert "COMMENT ON TABLE wallets IS" in str(SetTableComment(wallets).compile(dialect=postgresql.dialect()))
        column_ddl = str(SetColumnComment(wallets.c.balance).compile(dialect=postgresql.dialect()))
        assert "COMMENT ON COLUMN wallets.balance IS" in column_ddl
        assert "Balance in major units" in column_ddl and "\U0001F4B0" in column_ddl


def test_mermaid_shows_sanitized_field_descriptions_as_attribute_comments():
    diagram = render_mermaid(load_erd(FIXTURE))
    assert "int id PK \"Primary key 'id' \\ path\"" in diagram
    assert 'decimal balance "Balance in major units - wallet \U0001F4B0, it\'s \'exact\' second line"' in diagram
    assert 'string label "Plain label"' in diagram
    assert "string plain\n" in diagram + "\n"   # no comment when there is no description


def test_a_project_without_descriptions_does_not_import_pydantic_field(tmp_path):
    state = translate(load_erd(f"{FIXTURES}/valid_minimal.yml"))
    codebase_dir = CodeGenerator(output_dir=str(tmp_path / "w")).generate_project(state, force=True)
    schemas_src = (codebase_dir / "modules" / "widgets" / "schemas.py").read_text(encoding="utf-8")
    assert ", Field" not in schemas_src and "Field(" not in schemas_src   # ("Fields required..." docstrings are fine)
