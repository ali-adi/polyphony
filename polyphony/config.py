from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from polyphony.workspace import normalize_rel

DEFAULT_MODELS = {"code": "gemini-3.8-flash-low", "report": "gemini-3.8-flash-low"}

DEFAULT_HOME = Path.home() / ".polyphony"

REPO_FILE = ".polyphony.yaml"

PROJECTS_DIR = Path(__file__).resolve().parents[1] / "projects"


class ConfigError(Exception):
    pass


@dataclass
class ProjectConfig:
    name: str
    path: Path
    provision: list[dict] = field(default_factory=list)
    models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    check: str | None = None
    check_timeout_minutes: int = 10
    max_parallel: int | None = None
    source: Path | None = None
    allow_secrets: list[str] = field(default_factory=list)
    env_scrub: list[str] = field(default_factory=list)


def load_project(file: Path, repo: Path | None = None) -> ProjectConfig:
    try:
        data = yaml.safe_load(Path(file).read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"{file}: not valid YAML: {e}") from e
    data = {} if data is None else data
    if not isinstance(data, dict):
        raise ConfigError(f"{file}: expected a mapping of settings.")

    if repo is not None:
        data.setdefault("name", repo.name)
        path = (repo / Path(str(data.get("path") or ".")).expanduser()).resolve()
        if path != repo:
            raise ConfigError(
                f"{file}: path {data['path']!r} is not the repository the file is in; "
                "remove it, since it defaults to that repository."
            )
        data["path"] = str(path)
    for key in ("name", "path"):
        if not data.get(key):
            raise ConfigError(f"{file}: missing required key {key!r}.")

    models = data.get("models") or {}
    if not isinstance(models, dict) or set(models) - set(DEFAULT_MODELS):
        raise ConfigError(
            f"{file}: 'models' maps a mode ({', '.join(DEFAULT_MODELS)}) to an agy model, "
            f"not {models!r}."
        )
    max_parallel = data.get("max_parallel")
    # YAML `true` is a bool, and bool is an int subclass
    if max_parallel is not None and (type(max_parallel) is not int or max_parallel < 1):
        raise ConfigError(f"{file}: max_parallel must be a positive integer, not {max_parallel!r}.")

    check = data.get("check")
    if check is not None and not isinstance(check, str):
        raise ConfigError(f"{file}: 'check' must be a shell command string.")
    check_timeout = data.get("check_timeout_minutes", 10)
    if isinstance(check_timeout, bool) or not isinstance(check_timeout, int) or check_timeout <= 0:
        raise ConfigError(f"{file}: 'check_timeout_minutes' must be a positive whole number.")
    globs = {}
    for key in ("allow_secrets", "env_scrub"):
        value = data.get(key) or []
        if not isinstance(value, list) or not all(isinstance(g, str) and g.strip() for g in value):
            raise ConfigError(f"{file}: '{key}' must be a list of glob patterns.")
        globs[key] = [g.strip() for g in value]
    provision = _provision_entries(file, data.get("provision"))

    return ProjectConfig(
        name=str(data["name"]),
        path=Path(data["path"]).expanduser().resolve(),
        provision=provision,
        models={**DEFAULT_MODELS, **{k: str(v) for k, v in models.items()}},
        check=(check or "").strip() or None,
        check_timeout_minutes=check_timeout,
        max_parallel=max_parallel,
        source=Path(file),
        **globs,
    )


def _provision_entries(file: Path, value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"{file}: 'provision' must be a list of {{path, mode}} entries.")
    entries = []
    for entry in value:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ConfigError(
                f"{file}: provision entry {entry!r} must be a mapping with a 'path', "
                "such as { path: node_modules, mode: clone }."
            )
        # git listings and `git clean -e` match literally, so `./data` or `data/` would match nothing
        rel = normalize_rel(entry["path"])
        if not rel or rel.startswith("/") or rel == ".." or rel.startswith("../"):
            raise ConfigError(
                f"{file}: provision path {entry['path']!r} must be a path inside the repository."
            )
        mode = entry.get("mode", "clone")
        if mode not in ("clone", "link"):
            raise ConfigError(
                f"{file}: provision mode {mode!r} for {rel!r} must be 'clone' or 'link'."
            )
        entries.append({**entry, "path": rel, "mode": mode})
    return entries


def find_project(
    repo: str | Path, projects_dir: Path | None = None, home: Path | None = None
) -> ProjectConfig | None:
    repo_path = Path(repo).expanduser().resolve()
    in_repo = repo_path / REPO_FILE
    if in_repo.is_file():
        return load_project(in_repo, repo=repo_path)

    if projects_dir is not None:
        dirs = [projects_dir]
    else:
        home = home or Path(os.environ.get("POLYPHONY_HOME") or DEFAULT_HOME)
        dirs = [Path(home).expanduser() / "projects", PROJECTS_DIR]
    for base in dirs:
        if not base.is_dir():
            continue
        for file in sorted(base.glob("*/project.yaml")):
            cfg = load_project(file)
            if cfg.path == repo_path:
                return cfg
    return None
