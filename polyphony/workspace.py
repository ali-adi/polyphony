"""One job's workspace: a private clone of the repository.

A clone rather than a git worktree, so the user's repository has nothing
written to it until they apply a job: no branch, no worktree record, no
objects. The clone's remote is removed, so an agent working inside it has
no route to the user's GitHub remote.

The clone starts at HEAD, then takes the working tree as it is now:
uncommitted edits, new files, and gitignored files. The edits and new files
are committed in the copy as a snapshot, so the job's diff is only what the
agent changed, not the user's own work in progress.

Secret-looking files (SECRET_PATTERNS) are the exception: an untracked or
gitignored `.env` is where a repository keeps its API keys, and copying it
would hand them to every agent. They are withheld unless the project's
`allow_secrets` names them. A tracked one is in HEAD, so the clone has it
regardless; withholding covers only what the overlay would add.
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from polyphony.guard import run_git

# Never copied from the working tree: environments, caches, and OS litter.
OVERLAY_SKIP = frozenset({
    ".git", "env", "venv", ".venv", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store",
})
# The names in OVERLAY_SKIP that are also ordinary source directory names
# (a web app's src/env/server.ts). One of these is skipped only where it is
# really an environment: a directory at the repo root, where virtualenvs live,
# or one anywhere holding a virtualenv's pyvenv.cfg or a conda env's
# conda-meta/. Elsewhere it is the user's source and is copied like any other.
ENVIRONMENT_NAMES = frozenset({"env", "venv", ".venv"})
OVERLAY_MAX_BYTES = 50 * 1024 * 1024
IGNORE_FILE = ".polyphonyignore"

# Untracked or gitignored files the overlay withholds, matched on the basename
# at any depth and ignoring case (patterns here are lower case): dotenv files, private keys and keystores, and the credential
# files of package managers and cloud SDKs. Only the private half of an SSH key
# pair matches (id_rsa, not id_rsa.pub). Templates meant to be copied, like
# .env.example, hold no real values and are let through (SECRET_TEMPLATES).
SECRET_PATTERNS = (
    ".env", ".env.*",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".netrc", ".npmrc", ".pypirc",
    "credentials.json", "service-account*.json",
)
SECRET_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template", ".env.dist"})
SNAPSHOT_MESSAGE = "polyphony: working-tree snapshot"


class WorkspaceError(Exception):
    """The workspace could not be created."""


class ProvisionError(WorkspaceError):
    """Raised when a workspace cannot be fully provisioned.

    Always fatal. A partially provisioned workspace produces test failures
    unrelated to the agent's work, which the calling agent would then chase
    as real regressions.
    """


@dataclass
class Workspace:
    source: Path
    path: Path
    git_dir: Path | None = None
    skipped: list[str] = field(default_factory=list)
    # Secret-looking paths the overlay left out (see SECRET_PATTERNS), repo-relative.
    withheld: list[str] = field(default_factory=list)
    allow_secrets: tuple[str, ...] = ()

    @classmethod
    def create(
        cls, source: str | Path, path: str | Path, exclude: tuple[str, ...] = (),
        git_dir: str | Path | None = None, allow_secrets: tuple[str, ...] = (),
    ) -> "Workspace":
        """Clone `source` at its current HEAD into `path`, then overlay its working tree.

        `exclude` holds repo-relative paths the overlay leaves alone, such as
        the ones `provision` will materialize itself.

        `git_dir` puts the clone's git directory there instead of in `path`,
        out of the executor's workspace; see copy_git. Its config as set up
        here is saved as the trusted one.

        `allow_secrets` holds globs, matched against the repo-relative path
        or the basename, for secret-looking files the copy should get anyway
        (a test suite's `.env.test`, say). The rest are listed in `withheld`.

        `--no-hardlinks` copies git's object files rather than sharing them.
        Shared (hard-linked) objects would let the copy write into the user's
        repository: git refreshes the timestamps of objects a commit reuses,
        and an agent writing into an object file would corrupt both.
        """
        source_path = Path(source).resolve()
        # Absolute, because the clone below runs from the source's parent and
        # everything after it from the caller's cwd: a relative `path` would
        # put the clone in one place and look for it in another.
        dest = Path(path).expanduser().resolve()
        if git_dir is not None:
            git_dir = Path(git_dir).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        separate = ["--separate-git-dir", str(git_dir)] if git_dir is not None else []
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
            ws._overlay(exclude)
        except (WorkspaceError, OSError) as exc:
            ws.remove()
            raise WorkspaceError(str(exc)) from exc
        except BaseException:
            # Anything unforeseen still must not leave a half-made clone behind.
            ws.remove()
            raise
        if ws.git_dir is not None:
            shutil.copyfile(ws.git_dir / "config", trusted_config(ws.git_dir))
        return ws

    def _overlay(self, exclude: tuple[str, ...]) -> None:
        """Bring the source's uncommitted state into the copy and snapshot it."""
        src = str(self.source)
        # Provision paths name one repo-relative path each, so they match only
        # that path and what is under it: provisioning `models` must not drop
        # an untracked src/models/*.py. .polyphonyignore lines are globs,
        # matched against the path and against each component at any depth.
        anchored = [normalize_rel(p) for p in exclude if p.strip()]
        patterns: list[str] = []
        ignore_file = self.source / IGNORE_FILE
        if ignore_file.is_file():
            patterns += [
                line.strip().rstrip("/")
                for line in ignore_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]

        # Edits to tracked files, staged or not, including deletions and binaries.
        # A file staged but never committed is in this diff too, so a staged
        # secret is excluded from it by name.
        added = _git_names(["diff", "--name-only", "-z", "--no-renames", "--diff-filter=A", "HEAD"], src)
        staged_secrets = [r for r in added if self._secret(r)]
        self.withheld += staged_secrets
        patch = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--",
             *(f":(exclude,literal){r}" for r in staged_secrets)],
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

        # New files, then gitignored ones (listed per directory, so walk those).
        for flags in (["--others", "--exclude-standard"],
                      ["--others", "--ignored", "--exclude-standard", "--directory"]):
            for rel in _git_names(["ls-files", "-z", *flags], src):
                self._copy_tree(rel.rstrip("/"), patterns, anchored)
        self.withheld = sorted(set(self.withheld))  # the two listings can overlap

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
        """Copy one listed path (a file, or a directory of ignored files) into the copy."""
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
            if self._secret(r):
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

    def _secret(self, rel: str) -> bool:
        """Whether the overlay withholds `rel`: its basename looks like a
        secret, and no allow_secrets glob names it.

        Case is ignored on both sides, whatever the file system does: `.ENV`
        and `KEY.PEM` hold keys as surely as `.env` and `key.pem`, and on
        macOS they may be the same file.
        """
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
        """Materialize gitignored paths the project declares it needs.

        `clone` uses APFS copy-on-write: near-instant, no disk cost until
        written, and genuinely isolated. `link` symlinks instead — it is a
        hole in the isolation boundary, since writes reach the real path,
        and exists only for paths too large to clone.
        """
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
                    # -c (clonefile) needs APFS; fall back to a plain recursive copy.
                    # macOS cp may have made dst before clonefile failed, and
                    # `cp -R src dst` onto an existing dst copies into dst/<name>.
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
    """A repo-relative path in one spelling: `./data/` and `data` are the same
    path, and a provision entry is compared with git's listings as a string."""
    rel = posixpath.normpath(path.strip())
    return "" if rel == "." else rel


def _git_names(args: list[str], cwd: str) -> list[str]:
    """The NUL-separated paths a git listing prints, as str.

    Read as bytes and decoded the way Python decodes file names (os.fsdecode,
    surrogateescape), since a path git prints need not be UTF-8: an untracked
    Latin-1 file name would otherwise fail every delegate on the repository.
    """
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=120)
    if res.returncode != 0:
        raise WorkspaceError(f"git {args[0]} failed: {res.stderr.decode(errors='replace').strip()}")
    return [os.fsdecode(n) for n in res.stdout.split(b"\0") if n]


def trusted_config(git_dir: str | Path) -> Path:
    """Where the config Polyphony set up for a job's git dir is kept."""
    return Path(f"{git_dir}.trusted-config")


def copy_git(
    args: list[str], git_dir: str | Path, work_tree: str | Path, timeout: int = 30
) -> subprocess.CompletedProcess:
    """Run git on a job's copy using only what Polyphony set up there.

    The executor can write anything in its copy, and possibly the git dir
    beside it. Git runs code named in its config (fsmonitor, filters,
    include.path, hooksPath) and in hooks, and follows a `.git` file or a
    `commondir` file to another repository, where a commit would write into
    the user's own objects. So before every command: the trusted config is
    put back, commondir and alternates are removed, the copy's `.git`
    pointer is rewritten, and git gets the git dir and work tree explicitly,
    with hooks and fsmonitor off. Replaced files are unlinked rather than
    written through, since the executor may have made them symlinks.

    A job from before separate git dirs has its git dir inside the copy;
    it gets the flags, but has no trusted config to restore.
    """
    gd, wt = Path(git_dir), Path(work_tree)
    if gd.is_symlink():
        raise WorkspaceError(f"{gd} has been replaced by a symlink; refusing to run git there.")
    trusted = trusted_config(gd)
    if trusted.is_file() and not trusted.is_symlink():
        _unlink(gd / "config")
        shutil.copyfile(trusted, gd / "config")
    _unlink(gd / "commondir")
    _unlink(gd / "objects" / "info" / "alternates")
    if not gd.is_relative_to(wt):
        pointer = wt / ".git"
        wanted = f"gitdir: {gd}\n"
        if pointer.is_symlink() or not pointer.is_file() or pointer.read_bytes() != wanted.encode():
            _unlink(pointer)
            pointer.write_text(wanted)
    return run_git(
        ["--git-dir", str(gd), "--work-tree", str(wt),
         "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
        cwd=str(wt), timeout=timeout,
    )


def _unlink(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
