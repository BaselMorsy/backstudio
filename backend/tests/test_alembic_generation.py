# backend/tests/test_alembic_generation.py
import ast

from backend.erd.loader import load_erd
from backend.erd.translate import translate
from backend.services.code_generator import CodeGenerator

FIXTURES = "backend/tests/fixtures/erd"


def test_generates_alembic_scaffolding(tmp_path):
    erd = load_erd(f"{FIXTURES}/valid_minimal.yml")
    state = translate(erd)

    generator = CodeGenerator(output_dir=str(tmp_path))
    codebase_dir = generator.generate_project(state, force=True)

    assert (codebase_dir / "alembic.ini").exists()
    env_path = codebase_dir / "alembic" / "env.py"
    assert env_path.exists()
    assert (codebase_dir / "alembic" / "versions").is_dir()

    env_src = env_path.read_text(encoding="utf-8")
    ast.parse(env_src)
    assert "target_metadata = Base.metadata" in env_src
