from typer.testing import CliRunner

from backend.cli.main import app

runner = CliRunner()
FIXTURES = "backend/tests/fixtures/erd"


def test_generate_writes_codebase_and_reports_path(tmp_path):
    result = runner.invoke(
        app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Generated at:" in result.output
    assert (tmp_path / "Demo" / "codebase" / "server.py").exists()
    assert (tmp_path / "Demo" / "codebase" / "widgets" / "routes.py").exists()


def test_generate_refuses_to_overwrite_without_force(tmp_path):
    runner.invoke(app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)])
    result = runner.invoke(app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)])
    assert result.exit_code == 1
    assert "--force" in result.output


def test_generate_force_overwrites(tmp_path):
    runner.invoke(app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)])
    result = runner.invoke(
        app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path), "--force"]
    )
    assert result.exit_code == 0


def test_generate_invalid_erd_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("project: [unterminated")
    result = runner.invoke(app, ["generate", str(bad), "--output", str(tmp_path)])
    assert result.exit_code == 1
