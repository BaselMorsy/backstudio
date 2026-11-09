import yaml

from app.erd.loader import load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator

FIXTURES = "app/tests/fixtures/erd"


def _generate(tmp_path, path):
    return CodeGenerator(output_dir=str(tmp_path / "w")).generate_project(translate(load_erd(path)), force=True)


def test_debug_defaults_to_false_so_nothing_is_logged_by_default(tmp_path):
    codebase = _generate(tmp_path, f"{FIXTURES}/builtin_invite.yml")
    config = (codebase / "config.py").read_text(encoding="utf-8")
    assert 'os.getenv("DEBUG", "False")' in config


def test_sql_echo_follows_the_erd_not_debug(tmp_path):
    codebase = _generate(tmp_path, f"{FIXTURES}/builtin_invite.yml")
    base = (codebase / "database" / "base.py").read_text(encoding="utf-8")
    assert "echo=False" in base
    assert "settings.DEBUG" not in base

    doc = yaml.safe_load(open(f"{FIXTURES}/builtin_invite.yml", encoding="utf-8"))
    doc["database"]["echo"] = True
    path = tmp_path / "echo.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    base = (_generate(tmp_path / "e", path) / "database" / "base.py").read_text(encoding="utf-8")
    assert "echo=True" in base


def test_async_engine_echo_also_follows_the_erd(tmp_path):
    codebase = _generate(tmp_path, f"{FIXTURES}/async_minimal.yml")
    base = (codebase / "database" / "base.py").read_text(encoding="utf-8")
    assert "echo=False" in base
    assert "settings.DEBUG" not in base


def test_readme_database_url_uses_the_shipped_postgres_driver(tmp_path):
    codebase = _generate(tmp_path, f"{FIXTURES}/db_url_postgres_sync.yml")
    readme = (codebase / "README.md").read_text(encoding="utf-8")
    assert "DATABASE_URL=postgresql+psycopg2://" in readme
    assert "DATABASE_URL=postgresql://" not in readme
    assert "DEBUG=False" in readme
