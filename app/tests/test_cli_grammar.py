from typer.testing import CliRunner

from app.cli.grammar import TOPICS
from app.cli.main import app

runner = CliRunner()


def test_grammar_no_topic_lists_top_level_keys():
    result = runner.invoke(app, ["grammar"])
    assert result.exit_code == 0
    for key in ("project", "database", "auth", "rbac", "entities", "services"):
        assert key in result.output
    assert "backstudio grammar <topic>" in result.output


def test_grammar_every_topic_exits_zero_and_echoes_its_own_block():
    for topic in TOPICS:
        result = runner.invoke(app, ["grammar", topic])
        assert result.exit_code == 0, f"topic '{topic}' failed: {result.output}"
        assert f"{topic}:" in result.output


def test_grammar_rls_topic_mentions_read_scope_and_header_bypass():
    result = runner.invoke(app, ["grammar", "rls"])
    assert result.exit_code == 0
    assert "read_scope" in result.output
    assert "bypass_roles" in result.output


def test_grammar_unknown_topic_exits_nonzero_and_lists_valid_topics():
    result = runner.invoke(app, ["grammar", "bogus"])
    assert result.exit_code == 1
    assert "Unknown topic 'bogus'" in result.output
    for topic in TOPICS:
        assert topic in result.output
