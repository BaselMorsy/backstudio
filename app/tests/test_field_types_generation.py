import ast
import os
import subprocess
import sys
from decimal import Decimal

from app.erd.loader import load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator
from app.tests.test_generated_project_runtime import _GeneratedProjectImporter, isolated_sys_path  # noqa: F401

FIXTURES = "app/tests/fixtures/erd"


def _generate(tmp_path, path=f"{FIXTURES}/field_types_showcase.yml"):
    state = translate(load_erd(path))
    return CodeGenerator(output_dir=str(tmp_path / "workspace")).generate_project(state, force=True)


def test_showcase_renders_the_new_types_and_byte_compiles(tmp_path):
    codebase_dir = _generate(tmp_path)
    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    ast.parse(models_src)
    assert "Table, BigInteger, Enum, Numeric, Uuid" in models_src
    assert "from decimal import Decimal" in models_src
    assert "from .enums import LedgerEntryStatus" in models_src
    assert 'BigInteger().with_variant(Integer(), "sqlite")' in models_src
    assert "Numeric(18, 2)" in models_src and "Numeric(10, 4)" in models_src
    assert "default=Decimal('0.5')" in models_src
    assert "Uuid(as_uuid=True)" in models_src
    assert "        DateTime(timezone=True),\n" in models_src       # booked_at
    assert "        DateTime,\n" in models_src                       # local_note_at (timezone: false)
    assert "Enum(LedgerEntryStatus, native_enum=False, create_constraint=True, name='ck_ledger_entries_status')" in models_src
    assert "default=LedgerEntryStatus.PENDING" in models_src
    assert "ForeignKey('ledger_entries.id')" in models_src
    assert "Column('ledger_line_id', BigInteger, ForeignKey('ledger_lines.id'), primary_key=True)" in models_src
    assert "Column('ledger_tag_id', BigInteger, ForeignKey('ledger_tags.id'), primary_key=True)" in models_src

    enums_src = (codebase_dir / "database" / "enums.py").read_text(encoding="utf-8")
    ast.parse(enums_src)
    assert "class LedgerEntryStatus(str, Enum):" in enums_src
    assert "PENDING = 'PENDING'" in enums_src   # python_value renders via repr

    schemas_src = (codebase_dir / "modules" / "ledger" / "schemas.py").read_text(encoding="utf-8")
    ast.parse(schemas_src)
    assert "from decimal import Decimal" in schemas_src
    assert "from uuid import UUID" in schemas_src
    assert "from database.enums import LedgerEntryStatus" in schemas_src
    assert "amount: Decimal\n" in schemas_src
    assert "fee: Optional[Decimal] = Decimal('0.5')" in schemas_src
    assert "ref: Optional[UUID] = None" in schemas_src
    assert "status: LedgerEntryStatus = LedgerEntryStatus.PENDING" in schemas_src

    result = subprocess.run([sys.executable, "-m", "compileall", "-q", str(codebase_dir)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_projects_without_new_types_have_no_enums_module(tmp_path):
    codebase_dir = _generate(tmp_path, f"{FIXTURES}/valid_minimal.yml")
    assert not (codebase_dir / "database" / "enums.py").exists()


def test_showcase_round_trips_over_http_on_sqlite(tmp_path, monkeypatch, isolated_sys_path):
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'showcase.db').as_posix()}")
    monkeypatch.setenv("DEBUG", "True")
    ref = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            created = client.post(
                "/ledger_entries",
                json={"amount": "12.50", "ref": ref, "booked_at": "2026-01-01T10:00:00+00:00",
                      "local_note_at": "2026-01-01T10:00:00"},
            )
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["id"] == 1 and isinstance(body["id"], int)   # BigInteger PK autoincrements on SQLite
            assert isinstance(body["amount"], str) and Decimal(body["amount"]) == Decimal("12.50")
            assert Decimal(body["fee"]) == Decimal("0.5")             # default 0.5 rendered as Decimal('0.5')
            assert body["ref"] == ref
            assert body["status"] == "PENDING"
            assert body["booked_at"].startswith("2026-01-01T10:00:00")

            fetched = client.get("/ledger_entries/1").json()
            assert fetched["ref"] == ref and Decimal(fetched["amount"]) == Decimal("12.50")

            posted = client.post("/ledger_entries", json={"amount": "1", "status": "POSTED"})
            assert posted.status_code == 201 and posted.json()["status"] == "POSTED"

            bogus = client.post("/ledger_entries", json={"amount": "1", "status": "BOGUS"})
            assert bogus.status_code == 422
            assert bogus.json()["detail"][0]["loc"] == ["body", "status"]

            line = client.post("/ledger_lines", json={"memo": "m", "ledger_entry_id": 1})
            assert line.status_code == 201, line.text
            assert line.json()["ledger_entry_id"] == 1 and isinstance(line.json()["id"], int)
            assert client.post("/ledger_lines", json={"memo": "m", "ledger_entry_id": 999}).status_code == 400

            tag = client.post("/ledger_tags", json={"label": "t"})
            assert tag.status_code == 201


def test_showcase_ddl_for_postgresql_and_mysql_is_correct(tmp_path, monkeypatch, isolated_sys_path):
    """No database or driver needed: compile the generated metadata against each dialect."""
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'ddl.db').as_posix()}")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        importlib.import_module("database.models")
        base = importlib.import_module("database.base")
        from sqlalchemy.dialects import mysql, postgresql
        from sqlalchemy.schema import CreateTable

        tables = {t.name: t for t in base.Base.metadata.sorted_tables}
        pg = {name: str(CreateTable(t).compile(dialect=postgresql.dialect())) for name, t in tables.items()}
        entry = pg["ledger_entries"]
        assert "id BIGSERIAL NOT NULL" in entry
        assert "amount NUMERIC(18, 2) NOT NULL" in entry
        assert "booked_at TIMESTAMP WITH TIME ZONE" in entry
        assert "local_note_at TIMESTAMP WITHOUT TIME ZONE" in entry
        assert "ref UUID" in entry
        assert "CONSTRAINT ck_ledger_entries_status CHECK (status IN ('PENDING', 'POSTED', 'VOIDED'))" in entry
        assert "ledger_entry_id BIGINT" in pg["ledger_lines"]
        assert "ledger_line_id BIGINT NOT NULL" in pg["ledger_line_ledger_tag"]
        assert "ledger_tag_id BIGINT NOT NULL" in pg["ledger_line_ledger_tag"]

        my = str(CreateTable(tables["ledger_entries"]).compile(dialect=mysql.dialect()))
        assert "id BIGINT NOT NULL AUTO_INCREMENT" in my
        assert "ref CHAR(32)" in my


def test_alembic_autogenerate_handles_the_new_types(tmp_path):
    codebase_dir = _generate(tmp_path)
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{(tmp_path / 'alembic.db').as_posix()}", "DEBUG": "True"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "showcase"],
        cwd=str(codebase_dir), capture_output=True, text=True, env=env, timeout=60,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    migration = next((codebase_dir / "alembic" / "versions").glob("*.py")).read_text(encoding="utf-8")
    assert "sa.Enum('PENDING', 'POSTED', 'VOIDED', name='ck_ledger_entries_status'" in migration
    assert "sa.Uuid()" in migration
    assert "sa.Numeric(precision=18, scale=2)" in migration
    assert "sa.DateTime(timezone=True)" in migration
    assert "sa.BigInteger()" in migration


def test_auth_injected_user_timestamps_stay_naive_in_generated_models(tmp_path):
    codebase_dir = _generate(tmp_path, "examples/personal_finance.yml")
    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    user_start = models_src.index("class User(Base):")
    user_end = models_src.find("\nclass ", user_start + 1)   # User is the last (alphabetical) model here
    user_src = models_src[user_start:] if user_end == -1 else models_src[user_start:user_end]
    assert "timezone=True" not in user_src
    assert "DateTime(timezone=True)" in models_src   # Transaction.occurred_at is a declared datetime


def test_decimal_defaults_written_as_float_int_and_string_render_exactly(tmp_path):
    import yaml

    path = tmp_path / "decimals.yml"
    decimal = {"type": "decimal", "precision": 10, "scale": 2}
    path.write_text(
        yaml.safe_dump(
            {
                "project": {"name": "Demo"},
                "database": {"type": "sqlite", "database_name": "d.db"},
                "entities": [
                    {
                        "name": "Price",
                        "fields": [
                            {"name": "id", "type": "integer", "primary_key": True},
                            {"name": "a", "default": 0.1, **decimal},
                            {"name": "b", "default": 0, **decimal},
                            {"name": "c", "default": "12.50", **decimal},
                        ],
                    }
                ],
                "services": [{"name": "prices", "entities": ["Price"]}],
            }
        )
    )
    codebase_dir = _generate(tmp_path, str(path))
    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    assert "default=Decimal('0.1')" in models_src
    assert "default=Decimal('0')" in models_src
    assert "default=Decimal('12.50')" in models_src


def test_uuid_field_with_a_default_generates_and_inserts_without_error(tmp_path, monkeypatch, isolated_sys_path):
    """Final review F2: Uuid(as_uuid=True) requires a real uuid.UUID at bind time, not the raw
    string - a naive python_value-rendered string default crashed on insert."""
    import yaml

    ref = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    path = tmp_path / "uuid_default.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "project": {"name": "Demo"},
                "database": {"type": "sqlite", "database_name": "d.db"},
                "entities": [
                    {
                        "name": "Thing",
                        "fields": [
                            {"name": "id", "type": "integer", "primary_key": True},
                            {"name": "label", "type": "string"},
                            {"name": "ref", "type": "uuid", "default": ref},
                        ],
                    }
                ],
                "services": [{"name": "things", "entities": ["Thing"]}],
            }
        )
    )
    codebase_dir = _generate(tmp_path, str(path))
    models_src = (codebase_dir / "database" / "models.py").read_text(encoding="utf-8")
    assert "from uuid import UUID" in models_src
    assert f"default=UUID('{ref}')" in models_src

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'uuid_default.db').as_posix()}")
    monkeypatch.setenv("DEBUG", "True")
    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            created = client.post("/things", json={"label": "x"})
            assert created.status_code == 201, created.text
            assert created.json()["ref"] == ref
