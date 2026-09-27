"""Per-repository settings: what a job's copy needs provisioned, and which
executors to prefer.

A repository with no config still works. It just gets no provisioning and
the default pool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from polyphony.executors import EXECUTORS

# Cheapest subscription first: Claude quota is the binding constraint.
DEFAULT_POOL = ["agy", "cursor", "claude"]

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


def load_project(file: Path) -> ProjectConfig:
    data = yaml.safe_load(Path(file).read_text()) or {}
    for key in ("name", "path"):
        if not data.get(key):
            raise ConfigError(f"{file}: missing required key {key!r}.")

    pool = list(data.get("pool") or DEFAULT_POOL)
    models = dict(data.get("models") or {})
    unknown = sorted((set(pool) | set(models)) - set(EXECUTORS))
    if unknown:
        raise ConfigError(
            f"{file}: unknown executor(s) {', '.join(unknown)}; "
            f"expected one of {', '.join(sorted(EXECUTORS))}."
        )

    return ProjectConfig(
        name=str(data["name"]),
        path=Path(data["path"]).expanduser().resolve(),
        provision=list(data.get("provision") or []),
        pool=pool,
        models={str(k): str(v) for k, v in models.items()},
    )


def find_project(repo: str | Path, projects_dir: Path | None = None) -> ProjectConfig | None:
    """The config whose `path` is this repository, if any."""
    repo_path = Path(repo).expanduser().resolve()
    base = projects_dir if projects_dir is not None else PROJECTS_DIR
    if not base.is_dir():
        return None
    for file in sorted(base.glob("*/project.yaml")):
        cfg = load_project(file)
        if cfg.path == repo_path:
            return cfg
    return None
