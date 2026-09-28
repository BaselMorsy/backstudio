import ast
import subprocess
import sys

from app.erd.loader import load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator
from app.tests.test_generated_project_runtime import _GeneratedProjectImporter, isolated_sys_path  # noqa: F401

FIXTURES = "app/tests/fixtures/erd"


def _generate(tmp_path):
    state = translate(load_erd(f"{FIXTURES}/enabled_actions_gating.yml"))
    return CodeGenerator(output_dir=str(tmp_path / "workspace")).generate_project(state, force=True)


def test_translate_exposes_enabled_actions_on_data_models_but_not_on_the_injected_user():
    state = translate(load_erd(f"{FIXTURES}/enabled_actions_gating.yml"))
    by_name = {m["name"]: m for m in state["data_models"]}
    assert by_name["Archive"]["enabled_actions"] == ["list", "read"]
    assert by_name["Sealed"]["enabled_actions"] == []
    assert by_name["Note"]["enabled_actions"] == ["create", "list", "read", "update", "delete"]
    with_auth = translate(load_erd(f"{FIXTURES}/valid_full.yml"))
    user = next(m for m in with_auth["data_models"] if m["name"] == "User")
    assert "enabled_actions" not in user


def test_repo_and_service_only_contain_functions_for_enabled_actions(tmp_path):
    codebase_dir = _generate(tmp_path)
    repo_src = (codebase_dir / "database" / "repo.py").read_text(encoding="utf-8")
    service_src = (codebase_dir / "modules" / "records" / "service.py").read_text(encoding="utf-8")
    ast.parse(repo_src)
    ast.parse(service_src)

    # get_*_by_id is ALWAYS generated: FK validation in other modules and update/delete use it.
    for present in (
        "def get_archive_by_id(", "def get_all_archives(", "def get_sealed_by_id(",
        "def create_note(", "def get_all_notes(", "def update_note(", "def delete_note(",
    ):
        assert present in repo_src, present
    for absent in (
        "def create_archive(", "def update_archive(", "def delete_archive(",
        "def create_sealed(", "def get_all_sealeds(", "def update_sealed(", "def delete_sealed(",
    ):
        assert absent not in repo_src, absent

    for present in (
        "def list_archives(", "def get_archive(", "def create_note(", "def list_notes(",
        "def get_note(", "def update_note(", "def delete_note(",
    ):
        assert present in service_src, present
    for absent in (
        "def create_archive(", "def update_archive(", "def delete_archive(", "def create_sealed(",
        "def list_sealeds(", "def get_sealed(", "def update_sealed(", "def delete_sealed(",
    ):
        assert absent not in service_src, absent

    result = subprocess.run([sys.executable, "-m", "compileall", "-q", str(codebase_dir)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_disabled_entity_is_still_a_valid_fk_target_and_has_no_mutating_routes(tmp_path, monkeypatch, isolated_sys_path):
    """Review Focus: an entity with no HTTP create (Archive) must still be usable as the FK
    target of another module's create - get_archive_by_id has to survive the gating."""
    codebase_dir = _generate(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'gating.db').as_posix()}")
    monkeypatch.setenv("DEBUG", "True")

    with _GeneratedProjectImporter(codebase_dir):
        import importlib

        server_module = importlib.import_module("server")
        database_base = importlib.import_module("database.base")
        database_models = importlib.import_module("database.models")
        from fastapi.testclient import TestClient

        with TestClient(server_module.app) as client:
            session = database_base.SessionLocal()
            try:
                archive = database_models.Archive(title="a")
                session.add(archive)
                session.commit()
                session.refresh(archive)
                archive_id = archive.id
            finally:
                session.close()

            assert client.get(f"/archives/{archive_id}").status_code == 200
            assert [a["id"] for a in client.get("/archives").json()] == [archive_id]
            assert client.post("/archives", json={"title": "x"}).status_code == 405
            assert client.delete(f"/archives/{archive_id}").status_code == 405
            assert client.get("/sealeds").status_code == 404

            created = client.post("/notes", json={"body": "n", "archive_id": archive_id})
            assert created.status_code == 201, created.text
            assert client.post("/notes", json={"body": "n", "archive_id": 999}).status_code == 400
