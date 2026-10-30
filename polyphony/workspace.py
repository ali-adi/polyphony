from __future__ import annotations

import fnmatch
import os
import posixpath
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from polyphony.guard import run_git

OVERLAY_SKIP = frozenset({
    ".git", "env", "venv", ".venv", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store",
})
ENVIRONMENT_NAMES = frozenset({"env", "venv", ".venv"})
OVERLAY_MAX_BYTES = 50 * 1024 * 1024
IGNORE_FILE = ".polyphonyignore"

SECRET_PATTERNS = (
    ".env", ".env.*", "*.env", ".envrc",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".netrc", ".npmrc", ".pypirc",
    "credentials.json", "service-account*.json",
)
SECRET_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template", ".env.dist"})
SNAPSHOT_MESSAGE = "polyphony: working-tree snapshot"

# user git config (diff.noprefix, diff.external, textconv, color.diff, diff.context, diff.relative, diff.submodule) would corrupt a patch fed to `git apply`
DIFF_FLAGS = (
    "--no-color", "--no-ext-diff", "--no-textconv", "--no-relative",
    "--src-prefix=a/", "--dst-prefix=b/", "-U3", "--submodule=short", "--find-renames",
)
# info/attributes outranks every .gitattributes in the tree, so a job cannot mark its own files `-diff` or `binary`
NEUTRAL_ATTRIBUTES = "* !diff\n"


class WorkspaceError(Exception):
    pass


class ProvisionError(WorkspaceError):
    pass


@dataclass
class Workspace:
    source: Path
    path: Path
    git_dir: Path | None = None
    skipped: list[str] = field(default_factory=list)
    withheld: list[str] = field(default_factory=list)
    allow_secrets: tuple[str, ...] = ()

    @classmethod
    def create(
        cls, source: str | Path, path: str | Path, exclude: tuple[str, ...] = (),
        git_dir: str | Path | None = None, allow_secrets: tuple[str, ...] = (),
    ) -> "Workspace":
        source_path = Path(source).resolve()
        dest = Path(path).expanduser().resolve()
        if git_dir is not None:
            git_dir = Path(git_dir).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        separate = ["--separate-git-dir", str(git_dir)] if git_dir is not None else []
        # --no-hardlinks: hard-linked objects would let the copy write into the source repository
        res = run_git(
            ["clone", "--no-hardlinks", "--quiet", *separate, str(source_path), str(dest)],
            cwd=str(source_path.parent),
            timeout=300,
        )
        ws = cls(source=source_path, path=dest,
                 git_dir=Path(git_dir) if git_dir is not None else None,
                 allow_secrets=tuple(allow_secrets))
        if res.returncode != 0:
            ws.remove()
            raise WorkspaceError(f"Could not copy {source_path}: {res.stderr.strip()}")
        if run_git(["rev-parse", "--verify", "-q", "HEAD"], cwd=str(dest)).returncode != 0:
            ws.remove()
            raise WorkspaceError(f"{source_path} has no commits to work from.")
        run_git(["remote", "remove", "origin"], cwd=str(dest))
        try:
            ws._overlay_working_tree(exclude)
        except (WorkspaceError, OSError) as exc:
            ws.remove()
            raise WorkspaceError(str(exc)) from exc
        except BaseException:
            ws.remove()
            raise
        if ws.git_dir is not None:
            shutil.copyfile(ws.git_dir / "config", trusted_config(ws.git_dir))
        return ws

    def _overlay_working_tree(self, exclude: tuple[str, ...]) -> None:
        src = str(self.source)
        anchored = [normalize_rel(p) for p in exclude if p.strip()]
        patterns: list[str] = []
        ignore_file = self.source / IGNORE_FILE
        if ignore_file.is_file():
            patterns += [
                line.strip().rstrip("/")
                for line in ignore_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]

        edited = _git_names(
            ["diff", "--name-only", "-z", "--no-renames", "--diff-filter=d", "HEAD"], src)
        edited_secrets = [r for r in edited if self._is_withheld(r)]
        self.withheld += edited_secrets
        patch = subprocess.run(
            ["git", "diff", "--binary", *DIFF_FLAGS, "HEAD", "--",
             *(f":(exclude,literal){r}" for r in edited_secrets)],
            cwd=src, capture_output=True, timeout=120,
        )
        if patch.returncode != 0:
            raise WorkspaceError(f"Could not read uncommitted edits: {patch.stderr.decode().strip()}")
        if patch.stdout:
            res = subprocess.run(
                ["git", "apply", "--binary", "--whitespace=nowarn", "-"],
                cwd=self.path, input=patch.stdout, capture_output=True,
            )
            if res.returncode != 0:
                raise WorkspaceError(f"Could not copy uncommitted edits: {res.stderr.decode().strip()}")

        # --directory lists an ignored directory as one entry, so _copy_tree walks it
        for flags in (["--others", "--exclude-standard"],
                      ["--others", "--ignored", "--exclude-standard", "--directory"]):
            for rel in _git_names(["ls-files", "-z", *flags], src):
                self._copy_tree(rel.rstrip("/"), patterns, anchored)
        self.withheld = sorted(set(self.withheld))

        run_git(["add", "-A"], cwd=str(self.path))
        if run_git(["diff", "--cached", "--quiet"], cwd=str(self.path)).returncode != 0:
            res = run_git(
                ["-c", "user.name=polyphony", "-c", "user.email=polyphony@localhost",
                 "commit", "--quiet", "--no-verify", "-m", SNAPSHOT_MESSAGE],
                cwd=str(self.path),
            )
            if res.returncode != 0:
                raise WorkspaceError(f"Could not snapshot the working tree: {res.stderr.strip()}")

    def _copy_tree(self, rel: str, patterns: list[str], anchored: list[str]) -> None:
        def skipped_name(parts: tuple[str, ...], i: int) -> bool:
            if parts[i] not in OVERLAY_SKIP:
                return False
            if parts[i] not in ENVIRONMENT_NAMES:
                return True
            d = self.source.joinpath(*parts[:i + 1])
            return d.is_dir() and (
                i == 0 or (d / "pyvenv.cfg").is_file() or (d / "conda-meta").is_dir()
            )

        def excluded(r: str) -> bool:
            parts = Path(r).parts
            return any(skipped_name(parts, i) for i in range(len(parts))) or any(
                r == p or r.startswith(p + "/") for p in anchored
            ) or any(
                r == p or r.startswith(p + "/") or fnmatch.fnmatch(r, p)
                or any(fnmatch.fnmatch(part, p) for part in parts)
                for p in patterns
            )

        root = self.source / rel
        if root.is_dir() and not root.is_symlink():
            files = []
            for dirpath, dirnames, filenames in os.walk(root):
                base = Path(dirpath).relative_to(self.source)
                dirnames[:] = [d for d in dirnames if not excluded(str(base / d))]
                files += [str(base / f) for f in filenames]
        else:
            files = [rel]
        for r in files:
            if excluded(r):
                continue
            if self._is_withheld(r):
                self.withheld.append(r)
                continue
            s, d = self.source / r, self.path / r
            if not s.is_symlink() and s.is_file() and s.stat().st_size > OVERLAY_MAX_BYTES:
                self.skipped.append(r)
                continue
            if d.exists() or d.is_symlink():
                continue
            d.parent.mkdir(parents=True, exist_ok=True)
            if s.is_symlink():
                d.symlink_to(os.readlink(s))
            elif s.is_file():
                shutil.copy2(s, d)

    def _is_withheld(self, rel: str) -> bool:
        # case-insensitive on both sides: on macOS `.ENV` and `.env` can be the same file
        low, name = rel.lower(), Path(rel).name.lower()
        if name in SECRET_TEMPLATES or not any(
            fnmatch.fnmatchcase(name, p) for p in SECRET_PATTERNS
        ):
            return False
        allowed = [p.lower() for p in self.allow_secrets]
        return not any(fnmatch.fnmatchcase(low, p) or fnmatch.fnmatchcase(name, p)
                       for p in allowed)

    def remove(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
        if self.git_dir is not None:
            shutil.rmtree(self.git_dir, ignore_errors=True)
            trusted_config(self.git_dir).unlink(missing_ok=True)

    def provision(self, entries: list[dict]) -> list[str]:
        provisioned: list[str] = []
        for entry in entries:
            rel = str(entry.get("path", "")).strip()
            mode = str(entry.get("mode", "clone")).strip()

            if not rel:
                raise ProvisionError("Provision entry is missing a 'path'.")
            if rel.startswith("/") or ".." in Path(rel).parts:
                raise ProvisionError(
                    f"Refusing to provision {rel!r}: paths must be relative to the repo root."
                )

            src = (self.source / rel).resolve()
            dst = (self.path / rel).resolve()

            if not src.exists():
                raise ProvisionError(
                    f"Cannot provision {rel!r}: {src} does not exist in {self.source}."
                )

            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() or dst.is_symlink():
                raise ProvisionError(f"Cannot provision {rel!r}: {dst} already exists.")

            if mode == "link":
                dst.symlink_to(src)
            elif mode == "clone":
                res = subprocess.run(
                    ["cp", "-Rc", str(src), str(dst)],
                    capture_output=True, text=True,
                )
                if res.returncode != 0:
                    # cp -c (clonefile) needs APFS and may leave dst behind, which a plain `cp -R` would copy into as dst/<name>
                    _unlink(dst)
                    res = subprocess.run(
                        ["cp", "-R", str(src), str(dst)],
                        capture_output=True, text=True,
                    )
                    if res.returncode != 0:
                        raise ProvisionError(
                            f"Cannot provision {rel!r}: {res.stderr.strip()}"
                        )
            else:
                raise ProvisionError(
                    f"Unknown provision mode {mode!r} for {rel!r}; expected 'clone' or 'link'."
                )

            provisioned.append(rel)
        return provisioned


def normalize_rel(path: str) -> str:
    rel = posixpath.normpath(path.strip())
    return "" if rel == "." else rel


def _git_names(args: list[str], cwd: str) -> list[str]:
    # git paths need not be UTF-8, so decode as Python does file names (surrogateescape)
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=120)
    if res.returncode != 0:
        raise WorkspaceError(f"git {args[0]} failed: {res.stderr.decode(errors='replace').strip()}")
    return [os.fsdecode(n) for n in res.stdout.split(b"\0") if n]


def trusted_config(git_dir: str | Path) -> Path:
    return Path(f"{git_dir}.trusted-config")


def copy_git(
    args: list[str], git_dir: str | Path, work_tree: str | Path, timeout: int = 30
) -> subprocess.CompletedProcess:
    gd, wt = Path(git_dir), Path(work_tree)
    # git writes through symlinks in its git dir (index, objects/, refs/), so refuse rather than repair
    if gd.is_symlink():
        raise WorkspaceError(f"{gd} has been replaced by a symlink; refusing to run git there.")
    planted = _first_symlink(gd)
    if planted is not None:
        raise WorkspaceError(
            f"{planted} in the job's git dir is a symlink, which git would write through; "
            "refusing to run git there."
        )
    trusted = trusted_config(gd)
    if trusted.is_file() and not trusted.is_symlink():
        _unlink(gd / "config")
        shutil.copyfile(trusted, gd / "config")
    # commondir and alternates point git at another repository's objects
    _unlink(gd / "commondir")
    _unlink(gd / "objects" / "info" / "alternates")
    info = gd / "info"
    if gd.is_dir():
        if info.is_symlink() or not info.is_dir():
            _unlink(info)
        info.mkdir(exist_ok=True)
        _unlink(info / "attributes")
        (info / "attributes").write_text(NEUTRAL_ATTRIBUTES)
    if not gd.is_relative_to(wt):
        pointer = wt / ".git"
        wanted = f"gitdir: {gd}\n"
        if pointer.is_symlink() or not pointer.is_file() or pointer.read_bytes() != wanted.encode():
            _unlink(pointer)
            pointer.write_text(wanted)
    # hooks and fsmonitor run code named in the copy's config
    return run_git(
        ["--git-dir", str(gd), "--work-tree", str(wt),
         "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
        cwd=str(wt), timeout=timeout,
    )


def _first_symlink(git_dir: Path) -> Path | None:
    # os.walk lists symlinked directories among dirs without following them
    for root, dirs, files in os.walk(git_dir):
        for name in (*dirs, *files):
            path = Path(root, name)
            if path.is_symlink():
                return path
    return None


def _unlink(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
