from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()


def test_cli_shows_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "backstudio" in result.output.lower()
