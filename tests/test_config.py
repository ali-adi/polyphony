"""Per-repository config: what a job's copy needs provisioned, which executors to prefer."""

from pathlib import Path

import pytest
import yaml

from polyphony.config import (
    DEFAULT_POOL,
    PROJECTS_DIR,
    REPO_FILE,
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
    assert cfg.provision == [{"path": "env", "mode": "clone"}]
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
        {"path": "env", "mode": "clone"},
        {"path": "datasets/smoke", "mode": "clone"},
        {"path": "datasets/tuning", "mode": "clone"},
    ]


def test_check_and_its_timeout_are_loaded(tmp_path):
    f = _write(tmp_path / "projects", "demo", {
        "name": "demo", "path": str(tmp_path),
        "check": "pytest -q", "check_timeout_minutes": 3,
    })
    cfg = load_project(f)
    assert cfg.check == "pytest -q"
    assert cfg.check_timeout_minutes == 3


def test_no_check_by_default(tmp_path):
    cfg = load_project(_write(tmp_path / "projects", "demo", {"name": "demo", "path": str(tmp_path)}))
    assert cfg.check is None
    assert cfg.check_timeout_minutes == 10


@pytest.mark.parametrize("bad", [{"check": ["pytest"]}, {"check_timeout_minutes": 0},
                                 {"check_timeout_minutes": "ten"}])
def test_malformed_check_settings_name_the_file(tmp_path, bad):
    f = _write(tmp_path / "projects", "demo", {"name": "demo", "path": str(tmp_path), **bad})
    with pytest.raises(ConfigError, match=str(f)):
        load_project(f)


def test_max_parallel_loads_and_defaults_to_empty(tmp_path):
    f = _write(tmp_path / "projects", "demo",
               {"name": "demo", "path": str(tmp_path), "max_parallel": {"agy": 2}})
    assert load_project(f).max_parallel == {"agy": 2}
    g = _write(tmp_path / "projects", "plain", {"name": "plain", "path": str(tmp_path)})
    assert load_project(g).max_parallel == {}


def test_unknown_executor_in_max_parallel_is_rejected(tmp_path):
    f = _write(tmp_path / "projects", "demo",
               {"name": "demo", "path": str(tmp_path), "max_parallel": {"gpt": 1}})
    with pytest.raises(ConfigError, match="gpt"):
        load_project(f)


@pytest.mark.parametrize("value", [0, -1, "two", 1.5, True])
def test_max_parallel_must_be_a_positive_integer(tmp_path, value):
    f = _write(tmp_path / "projects", "demo",
               {"name": "demo", "path": str(tmp_path), "max_parallel": {"agy": value}})
    with pytest.raises(ConfigError, match="max_parallel"):
        load_project(f)


def test_malformed_yaml_names_the_file(tmp_path):
    f = tmp_path / "projects" / "demo" / "project.yaml"
    f.parent.mkdir(parents=True)
    f.write_text("name: [unclosed\n")
    with pytest.raises(ConfigError, match=str(f)):
        load_project(f)


def test_non_mapping_file_names_the_file(tmp_path):
    f = tmp_path / "projects" / "demo" / "project.yaml"
    f.parent.mkdir(parents=True)
    f.write_text("- just\n- a list\n")
    with pytest.raises(ConfigError, match=str(f)):
        load_project(f)


@pytest.fixture
def no_legacy(monkeypatch, tmp_path):
    """Point the legacy package-relative dir somewhere empty."""
    monkeypatch.setattr("polyphony.config.PROJECTS_DIR", tmp_path / "legacy-none")


@pytest.mark.usefixtures("no_legacy")
def test_repo_file_needs_neither_name_nor_path(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text(yaml.safe_dump({"pool": ["cursor"]}))
    cfg = find_project(repo, home=tmp_path / "home")
    assert cfg is not None
    assert cfg.name == "myrepo"
    assert cfg.path == repo.resolve()
    assert cfg.pool == ["cursor"]
    assert cfg.source == repo / REPO_FILE


@pytest.mark.usefixtures("no_legacy")
def test_empty_repo_file_is_a_config_with_defaults(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text("")
    cfg = find_project(repo, home=tmp_path / "home")
    assert cfg is not None and cfg.pool == DEFAULT_POOL


@pytest.mark.usefixtures("no_legacy")
def test_repo_file_accepts_a_path_that_is_the_repo(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text(yaml.safe_dump({"name": "x", "path": "."}))
    cfg = find_project(repo, home=tmp_path / "home")
    assert cfg.name == "x" and cfg.path == repo.resolve()


@pytest.mark.usefixtures("no_legacy")
def test_repo_file_pointing_elsewhere_is_rejected(tmp_path):
    """A file in one repository must not make a job clone another."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text(yaml.safe_dump({"path": str(tmp_path / "other")}))
    with pytest.raises(ConfigError, match=str(repo / REPO_FILE)):
        find_project(repo, home=tmp_path / "home")


@pytest.mark.usefixtures("no_legacy")
def test_repo_file_wins_over_home_projects(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text(yaml.safe_dump({"name": "from-repo"}))
    _write(tmp_path / "home" / "projects", "demo", {"name": "from-home", "path": str(repo)})
    assert find_project(repo, home=tmp_path / "home").name == "from-repo"


@pytest.mark.usefixtures("no_legacy")
def test_home_projects_found_without_repo_file(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    f = _write(tmp_path / "home" / "projects", "demo", {"name": "from-home", "path": str(repo)})
    cfg = find_project(repo, home=tmp_path / "home")
    assert cfg.name == "from-home" and cfg.source == f


@pytest.mark.usefixtures("no_legacy")
def test_home_defaults_to_polyphony_home_env(tmp_path, monkeypatch):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    _write(tmp_path / "envhome" / "projects", "demo", {"name": "from-env", "path": str(repo)})
    monkeypatch.setenv("POLYPHONY_HOME", str(tmp_path / "envhome"))
    assert find_project(repo).name == "from-env"


def test_legacy_projects_dir_is_the_last_resort(tmp_path, monkeypatch):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    legacy = tmp_path / "legacy"
    _write(legacy, "demo", {"name": "legacy", "path": str(repo)})
    monkeypatch.setattr("polyphony.config.PROJECTS_DIR", legacy)
    assert find_project(repo, home=tmp_path / "home").name == "legacy"

    _write(tmp_path / "home" / "projects", "demo", {"name": "from-home", "path": str(repo)})
    assert find_project(repo, home=tmp_path / "home").name == "from-home"


def test_explicit_projects_dir_replaces_home_and_legacy(tmp_path, monkeypatch):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    legacy = tmp_path / "legacy"
    _write(legacy, "demo", {"name": "legacy", "path": str(repo)})
    monkeypatch.setattr("polyphony.config.PROJECTS_DIR", legacy)
    _write(tmp_path / "home" / "projects", "demo", {"name": "from-home", "path": str(repo)})
    assert find_project(repo, projects_dir=tmp_path / "none", home=tmp_path / "home") is None


def test_explicit_projects_dir_still_yields_to_repo_file(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text(yaml.safe_dump({"name": "from-repo"}))
    assert find_project(repo, projects_dir=tmp_path / "none").name == "from-repo"


@pytest.mark.usefixtures("no_legacy")
def test_malformed_repo_file_names_the_file(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text("pool: [agy\n")
    with pytest.raises(ConfigError, match=str(repo / REPO_FILE)):
        find_project(repo, home=tmp_path / "home")


@pytest.mark.usefixtures("no_legacy")
def test_repo_file_carries_the_check_and_job_limits(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text(yaml.safe_dump({
        "check": "pytest -q", "check_timeout_minutes": 4, "max_parallel": {"agy": 2, "codex": 1},
    }))
    cfg = find_project(repo, home=tmp_path / "home")
    assert (cfg.check, cfg.check_timeout_minutes) == ("pytest -q", 4)
    assert cfg.max_parallel == {"agy": 2, "codex": 1}


@pytest.mark.parametrize("bad", [{"check": ["pytest"]}, {"max_parallel": {"agy": 0}}])
@pytest.mark.usefixtures("no_legacy")
def test_repo_file_rejects_malformed_check_and_limits(tmp_path, bad):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / REPO_FILE).write_text(yaml.safe_dump(bad))
    with pytest.raises(ConfigError, match=str(repo / REPO_FILE)):
        find_project(repo, home=tmp_path / "home")


def test_allow_secrets_and_env_scrub_load_and_default_to_empty(tmp_path):
    f = _write(tmp_path / "projects", "demo", {
        "name": "demo", "path": str(tmp_path),
        "allow_secrets": [".env.test"], "env_scrub": ["AWS_*"],
    })
    cfg = load_project(f)
    assert cfg.allow_secrets == [".env.test"]
    assert cfg.env_scrub == ["AWS_*"]
    bare = load_project(_write(tmp_path / "p2", "demo", {"name": "demo", "path": str(tmp_path)}))
    assert bare.allow_secrets == [] and bare.env_scrub == []


@pytest.mark.parametrize("bad", [{"allow_secrets": ".env"}, {"allow_secrets": [1]},
                                 {"env_scrub": "AWS_*"}, {"env_scrub": [""]},
                                 {"env_scrub": {"AWS_*": True}}])
def test_malformed_secret_settings_name_the_file(tmp_path, bad):
    f = _write(tmp_path / "projects", "demo", {"name": "demo", "path": str(tmp_path), **bad})
    with pytest.raises(ConfigError, match=str(f)):
        load_project(f)


# Lane: workspace review fixes.

@pytest.mark.parametrize("provision", [
    ["node_modules"],
    "node_modules",
    [{"mode": "clone"}],
    [{"path": "../outside"}],
    [{"path": "/abs"}],
    [{"path": "."}],
    [{"path": "data", "mode": "copy"}],
])
def test_malformed_provision_entries_name_the_file(tmp_path, provision):
    f = _write(tmp_path / "projects", "demo",
               {"name": "demo", "path": str(tmp_path), "provision": provision})
    with pytest.raises(ConfigError, match=str(f)):
        load_project(f)


def test_provision_paths_are_normalized(tmp_path):
    f = _write(tmp_path / "projects", "demo", {
        "name": "demo", "path": str(tmp_path),
        "provision": [{"path": "./data/"}, {"path": "a//b/", "mode": "link"}],
    })
    assert load_project(f).provision == [
        {"path": "data", "mode": "clone"}, {"path": "a/b", "mode": "link"},
    ]
