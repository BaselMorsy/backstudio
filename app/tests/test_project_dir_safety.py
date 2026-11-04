import pytest

from app.erd.loader import ERDValidationError, load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator

FIXTURES = "app/tests/fixtures/erd"
VALID_MINIMAL = open(f"{FIXTURES}/valid_minimal.yml", encoding="utf-8").read()


def _state_named(name):
    state = translate(load_erd(f"{FIXTURES}/valid_minimal.yml"))
    state["name"] = name
    return state


@pytest.mark.parametrize("name", ["../escaped", r"..\escaped", "a/b/c", "/abs/path"])
def test_generated_project_always_lands_inside_the_output_directory(tmp_path, name):
    out = tmp_path / "out"
    project_dir = CodeGenerator(output_dir=str(out)).generate_project(_state_named(name), force=True)

    assert project_dir.resolve().parent == out.resolve()
    assert not (tmp_path / "escaped").exists()


def test_force_regeneration_never_deletes_outside_the_output_directory(tmp_path):
    sibling = tmp_path / "precious"
    sibling.mkdir()
    (sibling / "data.txt").write_text("keep me")

    CodeGenerator(output_dir=str(tmp_path / "out")).generate_project(_state_named("../precious"), force=True)

    assert (sibling / "data.txt").read_text() == "keep me"


@pytest.mark.parametrize("name", ["..", ".", "...", " . "])
def test_loader_rejects_project_names_that_cannot_be_a_directory_name(tmp_path, name):
    bad = tmp_path / "bad.yml"
    bad.write_text(VALID_MINIMAL.replace("name: Demo", f'name: "{name}"', 1), encoding="utf-8")
    with pytest.raises(ERDValidationError, match="project.name"):
        load_erd(bad)
