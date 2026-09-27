"""Per-repository config: what a job's copy needs provisioned, which executors to prefer."""

from pathlib import Path

import pytest
import yaml

from polyphony.config import (
    DEFAULT_POOL,
    PROJECTS_DIR,
    ConfigError,
    find_project,
    load_project,
)


def _write(projects: Path, name: str, data: dict) -> Path:
    f = projects / name / "project.yaml"
    f.parent.mkdir(parents=True)
    f.write_text(yaml.safe_dump(data))
    return f


def test_load_full_project(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = _write(tmp_path / "projects", "demo", {
        "name": "demo",
        "path": str(repo),
        "provision": [{"path": "env/", "mode": "clone"}],
        "pool": ["cursor", "agy"],
        "models": {"cursor": "composer-2.5"},
    })
    cfg = load_project(f)
    assert cfg.name == "demo"
    assert cfg.path == repo.resolve()
    assert cfg.provision == [{"path": "env/", "mode": "clone"}]
    assert cfg.pool == ["cursor", "agy"]
    assert cfg.models == {"cursor": "composer-2.5"}


def test_defaults_when_optional_keys_absent(tmp_path):
    f = _write(tmp_path / "projects", "demo", {"name": "demo", "path": str(tmp_path)})
    cfg = load_project(f)
    assert cfg.provision == []
    assert cfg.pool == DEFAULT_POOL
    assert cfg.models == {}


def test_default_pool_spends_cheapest_subscription_first():
    assert DEFAULT_POOL == ["agy", "cursor", "claude"]


@pytest.mark.parametrize("missing", ["name", "path"])
def test_missing_required_key_names_the_file(tmp_path, missing):
    data = {"name": "demo", "path": str(tmp_path)}
    del data[missing]
    f = _write(tmp_path / "projects", "demo", data)
    with pytest.raises(ConfigError, match=str(f)):
        load_project(f)


def test_unknown_executor_in_pool_is_rejected(tmp_path):
    f = _write(tmp_path / "projects", "demo",
               {"name": "demo", "path": str(tmp_path), "pool": ["agy", "gpt"]})
    with pytest.raises(ConfigError, match="gpt"):
        load_project(f)


def test_unknown_executor_in_models_is_rejected(tmp_path):
    f = _write(tmp_path / "projects", "demo",
               {"name": "demo", "path": str(tmp_path), "models": {"gpt": "x"}})
    with pytest.raises(ConfigError, match="gpt"):
        load_project(f)


def test_find_project_matches_resolved_repo_path(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    projects = tmp_path / "projects"
    _write(projects, "other", {"name": "other", "path": str(tmp_path / "elsewhere")})
    _write(projects, "demo", {"name": "demo", "path": str(repo)})
    cfg = find_project(repo / "sub" / "..", projects_dir=projects)
    assert cfg is not None and cfg.name == "demo"


def test_find_project_returns_none_for_unknown_repo(tmp_path):
    projects = tmp_path / "projects"
    _write(projects, "demo", {"name": "demo", "path": str(tmp_path / "a")})
    assert find_project(tmp_path / "b", projects_dir=projects) is None


def test_find_project_tolerates_missing_projects_dir(tmp_path):
    assert find_project(tmp_path, projects_dir=tmp_path / "nope") is None


def test_real_medicoder_config_provisions_what_its_tests_need():
    """Verified by the provisioning spike: without all three, tests fail."""
    cfg = load_project(PROJECTS_DIR / "medicoder" / "project.yaml")
    assert cfg.provision == [
        {"path": "env/", "mode": "clone"},
        {"path": "datasets/smoke/", "mode": "clone"},
        {"path": "datasets/tuning/", "mode": "clone"},
    ]
