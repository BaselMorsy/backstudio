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


def _write_warning_erd(tmp_path):
    import yaml

    path = tmp_path / "w.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "project": {"name": "Demo"},
                "database": {"type": "sqlite", "database_name": "d.db"},
                "entities": [
                    {"name": "Person", "fields": [{"name": "id", "type": "integer", "primary_key": True}]},
                    {
                        "name": "Order",
                        "fields": [{"name": "id", "type": "integer", "primary_key": True}],
                        "relationships": [{"name": "customer", "cardinality": "many-to-one", "target": "Person"}],
                    },
                ],
                "services": [{"name": "sales", "entities": ["Person", "Order"]}],
            }
        )
    )
    return path


def test_validate_prints_relationship_name_warning_before_ok_and_still_exits_zero(tmp_path):
    result = runner.invoke(app, ["validate", str(_write_warning_erd(tmp_path))])
    assert result.exit_code == 0
    assert "Warning: Order.customer -> Person" in result.output
    assert "OK:" in result.output
    assert result.output.index("Warning:") < result.output.index("OK:")


def test_validate_prints_no_warning_when_names_are_honored():
    result = runner.invoke(app, ["validate", f"{FIXTURES}/valid_full.yml"])
    assert result.exit_code == 0 and "Warning" not in result.output
