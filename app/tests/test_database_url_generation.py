import importlib

import pytest

from app.erd.loader import load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator
from app.tests.test_generated_project_runtime import _GeneratedProjectImporter, isolated_sys_path  # noqa: F401

FIXTURES = "app/tests/fixtures/erd"


def _generate(tmp_path, fixture):
    state = translate(load_erd(f"{FIXTURES}/{fixture}.yml"))
    return CodeGenerator(output_dir=str(tmp_path / "workspace")).generate_project(state, force=True)


CASES = [
    ("db_url_postgres_sync", None, "postgresql+psycopg2://dana_user@db.internal:5433/dana finance"),
    ("db_url_postgres_sync", "p@ss/w:rd%", "postgresql+psycopg2://dana_user:p%40ss%2Fw%3Ard%25@db.internal:5433/dana finance"),
    ("db_url_postgres_async", None, "postgresql+asyncpg://dana_user@db.internal:5433/dana finance"),
    ("db_url_postgres_async", "pw", "postgresql+asyncpg://dana_user:pw@db.internal:5433/dana finance"),
    ("db_url_mysql_sync", None, "mysql+pymysql://root@localhost/appdb"),
    # no username in the ERD: a DB_PASSWORD alone is ignored (no half-formed credentials)
    ("async_postgresql", "ignored-without-username", "postgresql+asyncpg://localhost/async_pg.db"),
    ("async_mysql", None, "mysql+aiomysql://localhost/async_mysql.db"),
]


@pytest.mark.parametrize("fixture,password,expected", CASES)
def test_default_database_url_is_built_from_the_database_block(fixture, password, expected, tmp_path, monkeypatch, isolated_sys_path):
    codebase_dir = _generate(tmp_path, fixture)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if password is None:
        monkeypatch.delenv("DB_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("DB_PASSWORD", password)

    with _GeneratedProjectImporter(codebase_dir):
        config = importlib.import_module("config")
        assert config.settings.DATABASE_URL == expected


def test_database_url_env_var_still_overrides_the_built_default(tmp_path, monkeypatch, isolated_sys_path):
    codebase_dir = _generate(tmp_path, "db_url_postgres_sync")
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://other/db")

    with _GeneratedProjectImporter(codebase_dir):
        assert importlib.import_module("config").settings.DATABASE_URL == "postgresql://other/db"


def test_special_characters_in_the_database_block_cannot_corrupt_the_generated_config(tmp_path, monkeypatch, isolated_sys_path):
    """Review Focus: a username with quotes/backslash/emoji must compile and be URL-quoted."""
    import yaml

    hostile = "we\"ird\\name \U0001F4B0"   # we"ird\name <emoji>
    path = tmp_path / "hostile.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "project": {"name": "Demo"},
                "database": {"type": "postgresql", "database_name": "db", "username": hostile},
                "entities": [{"name": "Widget", "fields": [{"name": "id", "type": "integer", "primary_key": True}]}],
                "services": [{"name": "widgets", "entities": ["Widget"]}],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    assert load_erd(path).database.username == hostile   # sanity: it survived YAML unchanged
    state = translate(load_erd(path))
    codebase_dir = CodeGenerator(output_dir=str(tmp_path / "w")).generate_project(state, force=True)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    with _GeneratedProjectImporter(codebase_dir):
        url = importlib.import_module("config").settings.DATABASE_URL
    assert url == "postgresql+psycopg2://we%22ird%5Cname%20%F0%9F%92%B0@localhost/db"


def test_database_name_is_not_url_quoted_so_sqlalchemy_parses_it_back_exactly(tmp_path, monkeypatch, isolated_sys_path):
    """Review Focus (final review F1): SQLAlchemy's URL parser only un-quotes the
    username/password components, not the database name - quoting it would make the app
    connect to a literally-percent-encoded database name instead of the real one."""
    from sqlalchemy.engine import make_url

    codebase_dir = _generate(tmp_path, "db_url_postgres_sync")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "p@ss/w:rd%")

    with _GeneratedProjectImporter(codebase_dir):
        url = make_url(importlib.import_module("config").settings.DATABASE_URL)
    assert url.database == "dana finance"
    assert url.username == "dana_user"
    assert url.password == "p@ss/w:rd%"
    assert url.host == "db.internal" and url.port == 5433


def test_non_sqlite_config_has_no_sqlite_fallback_and_sqlite_config_is_unchanged(tmp_path):
    pg_src = (_generate(tmp_path / "a", "db_url_postgres_sync") / "config.py").read_text(encoding="utf-8")
    assert "sqlite" not in pg_src and "def _default_database_url" in pg_src and "from urllib.parse import quote" in pg_src
    sqlite_src = (_generate(tmp_path / "b", "valid_minimal") / "config.py").read_text(encoding="utf-8")
    assert "sqlite:///./demo.db" in sqlite_src and "_default_database_url" not in sqlite_src


def test_readme_env_example_matches_the_drivers_in_requirements(tmp_path):
    mysql_readme = (_generate(tmp_path / "m", "db_url_mysql_sync") / "README.md").read_text(encoding="utf-8")
    assert "DATABASE_URL=mysql+pymysql://" in mysql_readme and "DATABASE_URL=mysql://" not in mysql_readme
    assert "DB_PASSWORD" in mysql_readme
    pg_readme = (_generate(tmp_path / "p", "db_url_postgres_sync") / "README.md").read_text(encoding="utf-8")
    assert "DATABASE_URL=postgresql://user:password@db.internal:5433/dana finance" in pg_readme
    sqlite_readme = (_generate(tmp_path / "s", "valid_minimal") / "README.md").read_text(encoding="utf-8")
    assert "DB_PASSWORD" not in sqlite_readme
