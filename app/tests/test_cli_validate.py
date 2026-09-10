from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()
FIXTURES = "app/tests/fixtures/erd"


def test_validate_valid_file_exits_zero():
    result = runner.invoke(app, ["validate", f"{FIXTURES}/valid_full.yml"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_validate_invalid_file_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("project: [unterminated")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 1
    assert "Invalid YAML" in result.output
