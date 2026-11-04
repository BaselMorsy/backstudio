import subprocess
import sys
from pathlib import Path

import pytest

from app.erd.loader import ERDValidationError, load_erd
from app.erd.translate import translate
from app.services.code_generator import CodeGenerator

FIXTURES = Path("app/tests/fixtures/erd")


def test_no_generated_project_has_unused_imports_undefined_names_or_syntax_errors(tmp_path):
    generated = 0
    for fixture in sorted(FIXTURES.glob("*.yml")):
        try:
            erd = load_erd(fixture)
        except ERDValidationError:
            continue  # deliberately-invalid fixtures exercise the validators, not generation
        CodeGenerator(output_dir=str(tmp_path / fixture.stem)).generate_project(translate(erd), force=True)
        generated += 1
    assert generated > 20, "expected to generate most fixtures"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(tmp_path),
            "--isolated",
            "--no-cache",
            "--select",
            "F401,F821,F822,F823,E9",
            "--output-format",
            "concise",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 127 or "No module named ruff" in result.stderr:
        pytest.skip("ruff is not installed")
    assert result.returncode == 0, result.stdout + result.stderr
