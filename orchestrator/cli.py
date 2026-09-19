"""Click CLI entry point for ai-orch."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
import click
import yaml

from migrate.scanner import scan_project
from migrate.classifier import classify_items, ClassificationScope
from migrate.translator import translate_project


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """ai-orch: Local-first, multi-agent engineering orchestrator."""
    pass


@cli.command("migrate")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--name", "-n", default=None, help="Name of project (defaults to directory name)")
@click.option("--output", "-o", default=".", help="Root directory of ai-orch")
def migrate_cmd(project_path: str, name: Optional[str], output: str):
    """Scan existing repo AI config and migrate to ai-orch format."""
    p_path = Path(project_path).resolve()
    p_name = name or p_path.name
    out_root = Path(output).resolve()

    click.secho(f"\n🔍 Scanning project for AI configurations: {p_path}", fg="cyan", bold=True)
    scanned_items = scan_project(p_path)

    click.echo(f"   Found {len(scanned_items)} AI configuration and context items.")

    click.secho(f"📋 Classifying discovered items...", fg="cyan")
    classified_items = classify_items(scanned_items, p_name)

    global_count = sum(1 for c in classified_items if c.scope == ClassificationScope.GLOBAL)
    project_count = sum(1 for c in classified_items if c.scope == ClassificationScope.PROJECT)
    executor_count = sum(1 for c in classified_items if c.scope == ClassificationScope.EXECUTOR)
    sensitive_count = sum(1 for c in classified_items if c.scope == ClassificationScope.SENSITIVE)
    ephemeral_count = sum(1 for c in classified_items if c.scope == ClassificationScope.EPHEMERAL)

    click.echo(f"   • Global assets:   {global_count}")
    click.echo(f"   • Project assets:  {project_count}")
    click.echo(f"   • Executor shims:  {executor_count}")
    click.echo(f"   • Sensitive (.env):{sensitive_count} (blocked from copying)")
    click.echo(f"   • Ephemeral state: {ephemeral_count} (ignored)")

    click.secho(f"🚀 Translating into orchestrator knowledge layer...", fg="cyan")
    report = translate_project(
        project_path=p_path,
        output_root=out_root,
        classified_items=classified_items,
        project_name=p_name,
    )

    click.secho(f"\n✨ Migration complete for '{p_name}'!", fg="green", bold=True)
    click.echo(f"   • Original snapshot:  migration/{p_name}/original/")
    click.echo(f"   • Human Inventory:    {report.inventory_path}")
    click.echo(f"   • Structured Manifest:{report.manifest_path}")
    click.echo(f"   • Project Config:     {report.project_yaml_path}")
    click.echo(f"   • Safety Policies:    {report.safety_md_path}")
    click.echo(f"   • Context Knowledge:  {report.context_md_path}")
    click.echo(f"   • Project Skills ({len(report.project_skills_created)}):   {', '.join(report.project_skills_created) if report.project_skills_created else 'none'}")
    click.echo(f"   • Global Skills ({len(report.global_skills_created)}):    {', '.join(report.global_skills_created) if report.global_skills_created else 'none'}")
    click.echo("")


@cli.group("project")
def project_group():
    """Manage registered projects."""
    pass


@project_group.command("list")
@click.option("--orch-root", default=".", help="ai-orch root directory")
def project_list(orch_root: str):
    """List all registered projects."""
    projects_dir = Path(orch_root).resolve() / "projects"
    if not projects_dir.exists():
        click.echo("No projects directory found.")
        return

    projects = [p for p in projects_dir.iterdir() if p.is_dir() and (p / "project.yaml").exists()]
    if not projects:
        click.echo("No registered projects found.")
        return

    click.secho(f"\nRegistered Projects ({len(projects)}):", fg="cyan", bold=True)
    for p in sorted(projects):
        try:
            with open(p / "project.yaml", "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            name = data.get("name", p.name)
            desc = data.get("description", "")
            path = data.get("path", "")
            lead = data.get("executors", {}).get("lead", "claude")
            primary = data.get("executors", {}).get("primary", "agy")
            click.echo(f"  • {click.style(name, bold=True)} ({path})")
            click.echo(f"    Desc: {desc}")
            click.echo(f"    Executors: lead={lead}, primary={primary}")
        except Exception as e:
            click.echo(f"  • {p.name} (error loading config: {e})")
    click.echo("")


@cli.command("start")
@click.argument("project_name")
@click.option("--goal", "-g", required=True, help="Task objective or goal description")
@click.option("--read-only", "-r", is_flag=True, default=False, help="Run in read-only inspection mode (no file edits)")
@click.option("--max-iterations", "-m", default=10, type=int, help="Maximum allowed reasoning/execution loops")
@click.option("--lead", default=None, help="Force specific lead reasoner ('claude' or 'agy')")
@click.option("--orch-root", default=".", help="Root directory of ai-orch")
def start_cmd(project_name: str, goal: str, read_only: bool, max_iterations: int, lead: Optional[str], orch_root: str):
    """Start an autonomous multi-agent task on a project."""
    from orchestrator.main import Orchestrator

    try:
        orch = Orchestrator(
            project_name=project_name,
            root_dir=orch_root,
            read_only=read_only,
            max_iterations=max_iterations,
            preferred_lead=lead,
        )
        orch.run_task(goal=goal)
    except Exception as e:
        click.secho(f"\n❌ Execution failed: {e}", fg="red", bold=True)
        sys.exit(1)


@cli.group("task")
def task_group():
    """Inspect and manage tasks."""
    pass


@task_group.command("list")
@click.argument("project_name")
@click.option("--orch-root", default=".", help="Root directory of ai-orch")
def task_list_cmd(project_name: str, orch_root: str):
    """List tasks recorded for a project."""
    from orchestrator.state import StateManager

    state_mgr = StateManager(orch_root)
    tasks = state_mgr.list_tasks(project_name)

    if not tasks:
        click.echo(f"No tasks found for project '{project_name}'.")
        return

    click.secho(f"\nTasks for '{project_name}' ({len(tasks)}):", fg="cyan", bold=True)
    for t in tasks:
        color = "green" if t.status.value == "completed" else ("red" if t.status.value == "failed" else "yellow")
        status_styled = click.style(t.status.value.upper(), fg=color, bold=True)
        click.echo(f"  • {click.style(t.task_id, bold=True)} [{status_styled}]")
        click.echo(f"    Goal: {t.goal}")
        click.echo(f"    Iterations: {len(t.iterations)}/{t.max_iterations} | Started: {t.start_time}")
        if t.all_files_changed:
            click.echo(f"    Files changed: {', '.join(t.all_files_changed)}")
    click.echo("")


@task_group.command("status")
@click.argument("project_name")
@click.argument("task_id")
@click.option("--orch-root", default=".", help="Root directory of ai-orch")
def task_status_cmd(project_name: str, task_id: str, orch_root: str):
    """Display detailed status and iterations of a task."""
    from orchestrator.state import StateManager

    state_mgr = StateManager(orch_root)
    task = state_mgr.load_state(project_name, task_id)

    if not task:
        click.secho(f"Task '{task_id}' not found for project '{project_name}'.", fg="red")
        return

    color = "green" if task.status.value == "completed" else ("red" if task.status.value == "failed" else "yellow")
    click.secho(f"\nTask: {task.task_id}", fg="cyan", bold=True)
    click.echo(f"Project: {task.project_name} ({task.project_path})")
    click.echo(f"Status:  {click.style(task.status.value.upper(), fg=color, bold=True)}")
    click.echo(f"Goal:    {task.goal}")
    click.echo(f"Mode:    {'Read-Only' if task.read_only else 'Write / Autonomous'}")
    click.echo(f"Started: {task.start_time}")
    click.echo(f"Ended:   {task.end_time or 'In Progress'}")
    click.echo(f"Iterations: {len(task.iterations)} / {task.max_iterations}")

    if task.final_summary:
        click.secho("\nFinal Summary:", fg="green", bold=True)
        click.echo(task.final_summary)

    if task.error:
        click.secho(f"\nError: {task.error}", fg="red", bold=True)

    if task.iterations:
        click.secho("\nIteration History:", fg="magenta", bold=True)
        for it in task.iterations:
            click.echo(f"  [{it.iteration_number}] Reasoner: {it.reasoner_used} | Action: {it.lead_decision.get('action')} | Exec: {it.executor_used}")
            if it.files_changed:
                click.echo(f"      Files modified: {', '.join(it.files_changed)}")
    click.echo("")


if __name__ == "__main__":
    cli()
