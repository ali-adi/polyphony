"""Polyphony command line. The MCP server is the main interface; these
commands are for starting it and for a human checking on jobs."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import click

from polyphony import __version__
from polyphony.jobs import (
    DEFAULT_HOME,
    JobError,
    JobNotFound,
    JobStore,
    discard as discard_job,
    disk_usage,
    gc as gc_jobs,
)


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--home",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_HOME,
    envvar="POLYPHONY_HOME",
    show_default=True,
    help="Where job records and repository copies live.",
)
@click.pass_context
def cli(ctx, home):
    """Polyphony: hand isolated coding tasks to agent CLIs."""
    ctx.obj = JobStore(home)


@cli.command()
@click.option(
    "--projects-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory of <name>/project.yaml files, searched instead of "
    "$POLYPHONY_HOME/projects/ and the legacy projects/. A repository's own "
    ".polyphony.yaml still wins.",
)
@click.pass_obj
def mcp(store, projects_dir):
    """Serve the Polyphony tools over MCP on stdio."""
    from polyphony.server import build_server

    build_server(store=store, projects_dir=projects_dir).run("stdio")


@cli.command()
@click.argument("job_id", required=False)
@click.pass_obj
def jobs(store, job_id):
    """List recent jobs, or show one."""
    if job_id:
        try:
            job = store.refresh(store.load(job_id))
        except JobNotFound as e:
            raise click.ClickException(str(e))
        for key in ("id", "state", "executor", "model", "mode", "project", "workdir",
                    "exit_code", "error", "diff_stat", "check_command", "check_passed"):
            value = getattr(job, key)
            if value not in (None, ""):
                click.echo(f"{key:<10} {value}")
        if job.applied_paths:
            click.echo(f"{'applied':<10} {', '.join(job.applied_paths)}")
        click.echo(f"{'task':<10} {job.instruction}")
        if job.feedback:
            click.echo(f"{'attempt':<10} {job.attempt}")
            for i, note in enumerate(job.feedback, 1):
                click.echo(f"{f'revise {i}':<10} {note}")
        click.echo(f"{'output':<10} {store.output_path(job.id)}")
        return

    all_jobs = store.all()
    if not all_jobs:
        click.echo("No jobs.")
        return
    for job in all_jobs[:20]:
        job = store.refresh(job)
        created = datetime.fromtimestamp(job.created_at).strftime("%m-%d %H:%M")
        click.echo(f"{job.id}  {job.state:<9} {job.executor:<8} {created}  {job.instruction[:60]}")
    click.echo(f"{len(all_jobs)} job(s), {_size(disk_usage(store.dir))} on disk in {store.dir}")


@cli.command()
@click.argument("job_id")
@click.pass_obj
def discard(store, job_id):
    """Delete a finished job: its copy of the repository and its record."""
    try:
        discard_job(store, job_id)
    except (JobNotFound, JobError) as e:
        raise click.ClickException(str(e))
    click.echo(f"Discarded job {job_id}.")


_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


class Duration(click.ParamType):
    name = "duration"

    def convert(self, value, param, ctx):
        m = re.fullmatch(r"(\d+)([dhms])", str(value).strip())
        if not m:
            self.fail(f"{value!r} is not a duration like 7d, 12h, 30m or 45s.", param, ctx)
        return int(m.group(1)) * _UNITS[m.group(2)]


def _age(seconds: float) -> str:
    for unit, size in _UNITS.items():
        if seconds >= size or unit == "s":
            return f"{int(seconds // size)}{unit}"


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


@cli.command()
@click.option("--older-than", type=Duration(), required=True,
              help="Remove jobs that finished longer ago than this: 7d, 12h, 30m.")
@click.option("--dry-run", is_flag=True, help="List what would be removed; delete nothing.")
@click.pass_obj
def gc(store, older_than, dry_run):
    """Delete finished jobs older than a threshold, applied or not."""
    records = gc_jobs(store, older_than, dry_run=dry_run)
    if not records:
        click.echo("Nothing to remove.")
        return
    for r in records:
        click.echo(f"{r.job_id}  {r.state:<9} {_age(r.age_seconds):>5}  {_size(r.bytes)}")
    verb = "would free" if dry_run else "freed"
    click.echo(f"{len(records)} job(s), {verb} {_size(sum(r.bytes for r in records))}")


@cli.command()
@click.pass_obj
def stats(store):
    """Summarize how each executor's past jobs turned out."""
    from polyphony import ledger

    click.echo(ledger.format_summary(ledger.summarize(ledger.read(store.root))))


@cli.command()
@click.pass_obj
def doctor(store):
    """Show which agent CLIs are installed and usable, and which project
    config applies to the repository in the current directory."""
    from polyphony import executors
    from polyphony.config import ConfigError, find_project
    from polyphony.guard import run_git

    for name, cls in executors.EXECUTORS.items():
        ex = cls()
        mark = "ok     " if ex.is_available() else "MISSING"
        click.echo(f"{mark} {name:<8} {ex.binary_path or '-'}")

    res = run_git(["rev-parse", "--show-toplevel"], cwd=".")
    if res.returncode != 0:
        click.echo("config  - (not in a git repository)")
        return
    root = Path(res.stdout.strip())
    try:
        cfg = find_project(root, home=store.root)
    except ConfigError as e:
        raise click.ClickException(str(e))
    if cfg is None:
        click.echo(f"config  no config for {root}; default pool, no provisioning")
    else:
        click.echo(f"config  {cfg.source}")


@cli.command("usage")
@click.argument("executor", required=False)
def usage_cmd(executor):
    """Show how much quota agy and cursor have left."""
    from polyphony.usage import check_usage, format_usage

    try:
        results = check_usage([executor] if executor else None)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(format_usage(results))
