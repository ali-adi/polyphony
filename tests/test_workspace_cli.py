"""The workspace CLI group."""

import subprocess

import pytest
from click.testing import CliRunner

from orchestrator.cli import cli


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    (r / "app.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        cwd=r, check=True,
    )
    return r


def test_workspace_create_reports_the_path(repo, tmp_path):
    result = CliRunner().invoke(
        cli,
        ["workspace", "create", "proj", "task-cli1",
         "--repo", str(repo), "--root", str(tmp_path / "poly")],
    )
    assert result.exit_code == 0, result.output
    assert "task-cli1" in result.output


def test_workspace_clean_removes_it(repo, tmp_path):
    root = str(tmp_path / "poly")
    CliRunner().invoke(
        cli, ["workspace", "create", "proj", "task-cli2", "--repo", str(repo), "--root", root]
    )
    result = CliRunner().invoke(
        cli, ["workspace", "clean", "task-cli2", "--repo", str(repo), "--root", root]
    )
    assert result.exit_code == 0, result.output
    branches = subprocess.run(
        ["git", "branch", "--list", "polyphony/task-cli2"],
        cwd=repo, capture_output=True, text=True,
    )
    assert branches.stdout.strip() == ""
