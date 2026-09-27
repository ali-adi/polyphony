"""Per-repository settings: what a job's copy needs provisioned, and which
executors to prefer.

A repository with no config still works. It just gets no provisioning and
the default pool.

find_project looks in three places and the first match wins:

1. `<repo>/.polyphony.yaml`, in the repository itself.
2. `$POLYPHONY_HOME/projects/*/project.yaml` (POLYPHONY_HOME defaults to ~/.polyphony).
3. The package-relative `projects/` directory, which exists only in a source
   checkout (an editable install). Kept so existing configs there still work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from polyphony.executors import EXECUTORS
from polyphony.workspace import normalize_rel

# Cheapest subscription first: Claude quota is the binding constraint.
DEFAULT_POOL = ["agy", "cursor", "claude"]

# Active jobs allowed per executor, counted across every project (quota is per
# account). No limit unless a project sets max_parallel: real use has run seven
# cursor jobs at once, all applied.
DEFAULT_MAX_PARALLEL: int | None = None

# Here rather than in jobs.py, which imports this module.
DEFAULT_HOME = Path.home() / ".polyphony"

REPO_FILE = ".polyphony.yaml"

# Legacy: only present when running from a source checkout.
PROJECTS_DIR = Path(__file__).resolve().parents[1] / "projects"


class ConfigError(Exception):
    """A project file is malformed. Always names the file."""


@dataclass
class ProjectConfig:
    name: str
    path: Path
    provision: list[dict] = field(default_factory=list)
    pool: list[str] = field(default_factory=lambda: list(DEFAULT_POOL))
    models: dict[str, str] = field(default_factory=dict)
    # A shell command run in the job's copy after a code-mode executor succeeds.
    check: str | None = None
    check_timeout_minutes: int = 10
    max_parallel: dict[str, int] = field(default_factory=dict)
    # The file this came from; None for the no-config default.
    source: Path | None = None
    # Globs for secret-looking files the job's copy gets anyway (see
    # workspace.SECRET_PATTERNS), and for environment variables kept from both
    # the executor and the check.
    allow_secrets: list[str] = field(default_factory=list)
    env_scrub: list[str] = field(default_factory=list)


def load_project(file: Path, repo: Path | None = None) -> ProjectConfig:
    """Parse one project file. With repo, the file lives in that repository,
    so `name` and `path` default to it, and a `path` naming any other
    directory is an error: a file in one repository must not make a job
    clone another."""
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

    pool = list(data.get("pool") or DEFAULT_POOL)
    models = dict(data.get("models") or {})
    max_parallel = dict(data.get("max_parallel") or {})
    unknown = sorted((set(pool) | set(models) | set(max_parallel)) - set(EXECUTORS))
    if unknown:
        raise ConfigError(
            f"{file}: unknown executor(s) {', '.join(unknown)}; "
            f"expected one of {', '.join(sorted(EXECUTORS))}."
        )
    for name, cap in max_parallel.items():
        # bool is an int subclass; `true` in YAML is not a count.
        if type(cap) is not int or cap < 1:
            raise ConfigError(f"{file}: max_parallel for {name} must be a positive integer, not {cap!r}.")

    check = data.get("check")
    if check is not None and not isinstance(check, str):
        raise ConfigError(f"{file}: 'check' must be a shell command string.")
    check_timeout = data.get("check_timeout_minutes", 10)
    if isinstance(check_timeout, bool) or not isinstance(check_timeout, int) or check_timeout <= 0:
        raise ConfigError(f"{file}: 'check_timeout_minutes' must be a positive whole number.")
    globs = {}
    for key in ("allow_secrets", "env_scrub"):
        value = data.get(key) or []
        # A bare string would otherwise be iterated one character at a time.
        if not isinstance(value, list) or not all(isinstance(g, str) and g.strip() for g in value):
            raise ConfigError(f"{file}: '{key}' must be a list of glob patterns.")
        globs[key] = [g.strip() for g in value]
    provision = _provision_entries(file, data.get("provision"))

    return ProjectConfig(
        name=str(data["name"]),
        path=Path(data["path"]).expanduser().resolve(),
        provision=provision,
        pool=pool,
        models={str(k): str(v) for k, v in models.items()},
        check=(check or "").strip() or None,
        check_timeout_minutes=check_timeout,
        max_parallel=max_parallel,
        source=Path(file),
        **globs,
    )


def _provision_entries(file: Path, value: object) -> list[dict]:
    """The `provision` list, each entry checked and its path normalized.

    Checked here so a malformed entry is a ConfigError naming the file, not
    an AttributeError in create_job. Normalized because the path is compared
    as a string with git's listings (the overlay's exclude) and passed to
    `git clean -e`: `./data` or `data/` would match nothing there, so the
    overlay would copy it before provisioning, or clean would delete a link.
    """
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
    """The config for this repository, if any, in the order the module
    docstring gives. An explicit projects_dir replaces steps 2 and 3."""
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
