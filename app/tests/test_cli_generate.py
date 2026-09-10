from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()
FIXTURES = "app/tests/fixtures/erd"


def test_generate_writes_codebase_and_reports_path(tmp_path):
    result = runner.invoke(
        app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Generated at:" in result.output
    assert (tmp_path / "Demo" / "server.py").exists()
    assert (tmp_path / "Demo" / "modules" / "widgets" / "routes.py").exists()


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


def test_generate_writes_random_secret_when_auth_enabled_and_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)

    result = runner.invoke(app, ["generate", f"{FIXTURES}/valid_full.yml", "--output", str(tmp_path)])

    assert result.exit_code == 0
    assert "Generated a random JWT_SECRET" in result.output
    env_file = tmp_path / "ShopHub" / ".env"
    assert env_file.exists()
    content = env_file.read_text(encoding="utf-8")
    assert "JWT_SECRET=" in content
    secret_value = content.split("JWT_SECRET=")[1].split("\n")[0].strip()
    assert len(secret_value) >= 32  # a real random token, not a placeholder string


def test_generate_does_not_overwrite_existing_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)

    codebase_dir = tmp_path / "ShopHub"
    codebase_dir.mkdir(parents=True)
    (codebase_dir / ".env").write_text("JWT_SECRET=my-own-custom-secret\n", encoding="utf-8")

    result = runner.invoke(
        app, ["generate", f"{FIXTURES}/valid_full.yml", "--output", str(tmp_path), "--force"]
    )

    assert result.exit_code == 0
    assert "Generated a random JWT_SECRET" not in result.output
    assert (codebase_dir / ".env").read_text(encoding="utf-8") == "JWT_SECRET=my-own-custom-secret\n"


def test_generate_does_not_write_env_file_when_secret_already_set(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "already-exported-secret")

    result = runner.invoke(app, ["generate", f"{FIXTURES}/valid_full.yml", "--output", str(tmp_path)])

    assert result.exit_code == 0
    assert "Generated a random JWT_SECRET" not in result.output
    assert not (tmp_path / "ShopHub" / ".env").exists()


def test_generate_force_preserves_hand_edited_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)

    runner.invoke(app, ["generate", f"{FIXTURES}/valid_full.yml", "--output", str(tmp_path)])
    env_file = tmp_path / "ShopHub" / ".env"
    env_file.write_text("JWT_SECRET=my-hand-picked-secret\nEXTRA_VAR=keep-me\n", encoding="utf-8")

    result = runner.invoke(
        app, ["generate", f"{FIXTURES}/valid_full.yml", "--output", str(tmp_path), "--force"]
    )

    assert result.exit_code == 0
    assert "Generated a random JWT_SECRET" not in result.output
    assert env_file.read_text(encoding="utf-8") == "JWT_SECRET=my-hand-picked-secret\nEXTRA_VAR=keep-me\n"


def test_generate_does_not_write_env_file_when_auth_disabled(tmp_path):
    result = runner.invoke(
        app, ["generate", f"{FIXTURES}/valid_minimal.yml", "--output", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert not (tmp_path / "Demo" / ".env").exists()
