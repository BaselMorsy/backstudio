from typer.testing import CliRunner

from backend.cli.main import app

runner = CliRunner()
FIXTURES = "backend/tests/fixtures/erd"


def test_visualize_writes_html_file(tmp_path, monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda *_args, **_kwargs: True)
    out_file = tmp_path / "diagram.html"

    result = runner.invoke(
        app, ["visualize", f"{FIXTURES}/valid_minimal.yml", "--output", str(out_file), "--no-open"]
    )

    assert result.exit_code == 0
    assert out_file.exists()
    assert "erDiagram" in out_file.read_text(encoding="utf-8")
    assert "Diagram written to" in result.output


def test_visualize_invalid_file_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("project: [unterminated")
    result = runner.invoke(app, ["visualize", str(bad), "--no-open"])
    assert result.exit_code == 1
