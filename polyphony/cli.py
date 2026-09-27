"""Polyphony command line. The MCP server is the main interface; these
commands are for starting it and for a human checking on jobs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click

from polyphony import __version__
from polyphony.jobs import DEFAULT_HOME, JobError, JobNotFound, JobStore, discard as discard_job


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
    help="Directory of <name>/project.yaml files (default: the repo's projects/).",
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
                    "exit_code", "error", "diff_stat"):
            value = getattr(job, key)
            if value not in (None, ""):
                click.echo(f"{key:<10} {value}")
        click.echo(f"{'task':<10} {job.instruction}")
        click.echo(f"{'output':<10} {store.output_path(job.id)}")
        return

    all_jobs = store.all()
    if not all_jobs:
        click.echo("No jobs.")
        return
    for job in all_jobs[:20]:
        job = store.refresh(job)
        created = datetime.fromtimestamp(job.created_at).strftime("%m-%d %H:%M")
        click.echo(f"{job.id}  {job.state:<9} {job.executor:<6} {created}  {job.instruction[:60]}")


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


@cli.command()
def doctor():
    """Show which agent CLIs are installed and usable."""
    from polyphony.executors import EXECUTORS

    for name, cls in EXECUTORS.items():
        ex = cls()
        mark = "ok     " if ex.is_available() else "MISSING"
        click.echo(f"{mark} {name:<7} {ex.binary_path or '-'}")


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
