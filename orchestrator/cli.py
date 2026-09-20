"""Click CLI entry point for Polyphony."""

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
    """Polyphony: Local-first, multi-agent engineering orchestrator."""
    pass


@cli.command("migrate")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--name", "-n", default=None, help="Name of project (defaults to directory name)")
@click.option("--output", "-o", default=".", help="Root directory of Polyphony")
def migrate_cmd(project_path: str, name: Optional[str], output: str):
    """Scan existing repo AI config and migrate to Polyphony format."""
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
    click.echo(f"   • Conventions & Style:{report.conventions_md_path}")
    click.echo(f"   • Context Knowledge:  {report.context_md_path}")
    click.echo(f"   • Project Hooks ({len(report.hooks_migrated)}):    {', '.join(report.hooks_migrated)}")
    click.echo(f"   • Project Rules ({len(report.rules_migrated)}):    {', '.join(report.rules_migrated)}")
    click.echo(f"   • Project Skills ({len(report.project_skills_created)}):   {', '.join(report.project_skills_created) if report.project_skills_created else 'none'}")
    click.echo(f"   • Global Skills ({len(report.global_skills_created)}):    {', '.join(report.global_skills_created) if report.global_skills_created else 'none'}")
    click.echo("")


@cli.group("project")
def project_group():
    """Manage registered projects."""
    pass


@project_group.command("list")
@click.option("--orch-root", default=".", help="Polyphony root directory")
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
            models_info = data.get("models", {})
            lead_model_name = models_info.get("lead", {}).get(lead, {}).get("model", "default")
            primary_model_name = models_info.get("executors", {}).get(primary, {}).get("model", "default")
            click.echo(f"  • {click.style(name, bold=True)} ({path})")
            click.echo(f"    Desc: {desc}")
            click.echo(f"    Executors: lead={lead} [{lead_model_name}], primary={primary} [{primary_model_name}]")
        except Exception as e:
            click.echo(f"  • {p.name} (error loading config: {e})")
    click.echo("")


@project_group.command("add")
@click.argument("name")
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--orch-root", default=".", help="Polyphony root directory")
def project_add(name: str, path: str, orch_root: str):
    """Register an existing repository in Polyphony without full migration."""
    p_path = Path(path).resolve()
    if not p_path.exists() or not p_path.is_dir():
        click.secho(f"❌ Target directory does not exist: {p_path}", fg="red", bold=True)
        sys.exit(1)

    orch_dir = Path(orch_root).resolve()
    proj_dir = orch_dir / "projects" / name
    if (proj_dir / "project.yaml").exists():
        click.secho(f"⚠️ Project '{name}' already exists at {proj_dir}", fg="yellow", bold=True)
        return

    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "skills").mkdir(exist_ok=True)

    default_config = {
        "name": name,
        "path": str(p_path),
        "description": f"Registered repository at {p_path}",
        "executors": {
            "lead": "claude",
            "primary": "agy",
            "fallback": "cursor",
        },
        "safety": {
            "read_only": False,
            "require_tests_before_stop": True,
        },
        "tests": {
            "commands": ["pytest"],
        },
    }
    with open(proj_dir / "project.yaml", "w", encoding="utf-8") as f:
        yaml.dump(default_config, f, sort_keys=False)

    docs = {
        "context.md": f"# Project Context: {name}\n\nRepository: `{p_path}`\n",
        "conventions.md": f"# Coding Conventions: {name}\n\nFollow idiomatic patterns and existing codebase style.\n",
        "safety.md": f"# Safety Policies: {name}\n\n- Do not delete production configurations or sensitive credentials.\n",
        "architecture.md": f"# Architecture Overview: {name}\n\nCore modules and component responsibilities.\n",
        "decisions.md": f"# Architectural Decisions & Learnings: {name}\n\nDurable record of architectural choices and optimization conclusions.\n",
        "known_issues.md": f"# Known Issues: {name}\n\nKnown caveats, edge cases, and flakiness tracking.\n",
    }
    for doc_name, content in docs.items():
        doc_path = proj_dir / doc_name
        if not doc_path.exists():
            doc_path.write_text(content, encoding="utf-8")

    click.secho(f"✨ Successfully registered project '{name}'!", fg="green", bold=True)
    click.echo(f"   • Config:   {proj_dir / 'project.yaml'}")
    click.echo(f"   • Context:  {proj_dir / 'context.md'}")
    click.echo(f"   • Path:     {p_path}")


@project_group.command("inspect")
@click.argument("name")
@click.option("--orch-root", default=".", help="Polyphony root directory")
def project_inspect(name: str, orch_root: str):
    """Inspect registered context, skills, and configuration for a project."""
    from orchestrator.context import load_project_knowledge
    from orchestrator.models_config import resolve_models_config
    from orchestrator.safety import resolve_safety_config

    orch_dir = Path(orch_root).resolve()
    proj_dir = orch_dir / "projects" / name
    if not (proj_dir / "project.yaml").exists():
        click.secho(f"❌ Project '{name}' not found at {proj_dir}", fg="red", bold=True)
        sys.exit(1)

    try:
        knowledge = load_project_knowledge(name, orch_dir)
    except Exception as e:
        click.secho(f"❌ Error loading project '{name}': {e}", fg="red", bold=True)
        sys.exit(1)

    cfg = knowledge.get("config", {})
    global_path = orch_dir / "config" / "global.yaml"
    global_cfg = {}
    if global_path.exists():
        with open(global_path, "r", encoding="utf-8") as f:
            global_cfg = yaml.safe_load(f) or {}

    models_cfg = resolve_models_config(global_cfg=global_cfg, project_cfg=cfg)
    safety_cfg = resolve_safety_config(global_cfg=global_cfg, project_cfg=cfg)

    click.secho(f"\n🔍 Project Inspection: '{name}'", fg="cyan", bold=True)
    click.echo(f"   Path:        {knowledge.get('path', 'N/A')}")
    click.echo(f"   Description: {cfg.get('description', 'N/A')}")

    click.secho("\n📄 Knowledge & Context Files:", fg="yellow", bold=True)
    context_files = ["context.md", "conventions.md", "safety.md", "architecture.md", "decisions.md", "known_issues.md"]
    for cf in context_files:
        p = proj_dir / cf
        if p.exists():
            line_count = len(p.read_text(encoding="utf-8").splitlines())
            size_kb = p.stat().st_size / 1024.0
            click.echo(f"   • {click.style(cf, bold=True)} ({line_count} lines, {size_kb:.1f} KB)")
        else:
            click.echo(f"   • {cf} (not present)")

    click.secho("\n🧠 Skills:", fg="yellow", bold=True)
    proj_skills_dir = proj_dir / "skills"
    proj_skills = [s.name for s in proj_skills_dir.iterdir() if s.is_dir()] if proj_skills_dir.exists() else []
    global_skills_dir = orch_dir / "skills"
    global_skills = [s.name for s in global_skills_dir.iterdir() if s.is_dir()] if global_skills_dir.exists() else []

    click.echo(f"   • Project Skills ({len(proj_skills)}): {', '.join(sorted(proj_skills)) if proj_skills else 'None'}")
    click.echo(f"   • Global Skills ({len(global_skills)}):  {', '.join(sorted(global_skills)) if global_skills else 'None'}")

    test_cmds = cfg.get("tests", {}).get("commands", ["pytest"])
    click.secho("\n🧪 Test Commands:", fg="yellow", bold=True)
    for tc in test_cmds:
        click.echo(f"   • {tc}")

    click.secho("\n🛡️ Safety Policies:", fg="yellow", bold=True)
    click.echo(f"   • Read-Only:                 {safety_cfg.read_only}")
    click.echo(f"   • Require Tests Before Stop: {safety_cfg.require_tests_before_stop}")
    click.echo(f"   • Blocked Commands:          {len(safety_cfg.blocked_commands)}")
    click.echo(f"   • Protected Paths:           {len(safety_cfg.protected_paths)}")
    click.echo("")



@cli.command("start")
@click.argument("project_name")
@click.option("--goal", "-g", required=True, help="Task objective or goal description")
@click.option("--read-only", "-r", is_flag=True, default=False, help="Run in read-only inspection mode (no file edits)")
@click.option("--max-iterations", "-m", default=10, type=int, help="Maximum allowed reasoning/execution loops")
@click.option("--lead", default=None, help="Force specific lead reasoner ('claude' or 'agy')")
@click.option("--lead-model", default=None, help="Model override for the lead reasoner")
@click.option("--lead-thinking", default=None, help="Thinking effort/budget for lead reasoner (low, medium, high, or tokens)")
@click.option("--executor-model", default=None, help="Model override for executor agents")
@click.option("--executor-thinking", default=None, help="Thinking effort for executor agents (low, medium, high)")
@click.option("--subagent-model", default=None, help="Default model override for child subagents")
@click.option("--subagent-thinking", default=None, help="Default thinking effort for child subagents")
@click.option("--history-window", default=3, type=int, help="Number of past iterations to include in reasoning prompt")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate execution without modifying files or running commands")
@click.option("--token-budget", default=None, type=int, help="Total token budget allocated for the task")
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
def start_cmd(
    project_name: str,
    goal: str,
    read_only: bool,
    max_iterations: int,
    lead: Optional[str],
    lead_model: Optional[str],
    lead_thinking: Optional[str],
    executor_model: Optional[str],
    executor_thinking: Optional[str],
    subagent_model: Optional[str],
    subagent_thinking: Optional[str],
    history_window: int,
    dry_run: bool,
    token_budget: Optional[int],
    orch_root: str,
):
    """Start an autonomous multi-agent task on a project."""
    from orchestrator.main import Orchestrator

    cli_overrides = {
        "lead_model": lead_model,
        "lead_thinking": lead_thinking,
        "executor_model": executor_model,
        "executor_thinking": executor_thinking,
        "subagent_model": subagent_model,
        "subagent_thinking": subagent_thinking,
    }
    cli_overrides = {k: v for k, v in cli_overrides.items() if v is not None}

    try:
        orch = Orchestrator(
            project_name=project_name,
            root_dir=orch_root,
            read_only=read_only,
            max_iterations=max_iterations,
            preferred_lead=lead,
            cli_overrides=cli_overrides,
            history_window=history_window,
            dry_run=dry_run,
            token_budget=token_budget,
        )
        orch.run_task(goal=goal)
    except Exception as e:
        click.secho(f"\n❌ Execution failed: {e}", fg="red", bold=True)
        sys.exit(1)


@cli.command("resume")
@click.argument("project_name")
@click.argument("task_id")
@click.option("--max-iterations", "-m", default=10, type=int, help="Maximum allowed iterations for the resumed task")
@click.option("--history-window", default=3, type=int, help="Number of past iterations to include in reasoning prompt")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate execution without modifying files or running commands")
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
def resume_cmd(
    project_name: str,
    task_id: str,
    max_iterations: int,
    history_window: int,
    dry_run: bool,
    orch_root: str,
):
    """Resume an existing, paused, or failed task."""
    from orchestrator.main import Orchestrator

    try:
        orch = Orchestrator(
            project_name=project_name,
            root_dir=orch_root,
            max_iterations=max_iterations,
            history_window=history_window,
            dry_run=dry_run,
        )
        orch.resume_task(task_id=task_id)
    except Exception as e:
        click.secho(f"\n❌ Resume failed: {e}", fg="red", bold=True)
        sys.exit(1)


@cli.group("task")
def task_group():
    """Inspect and manage tasks."""
    pass


@task_group.command("list")
@click.argument("project_name")
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
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
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
def task_status_cmd(project_name: str, task_id: str, orch_root: str):
    """Display detailed status and iterations of a task."""
    from orchestrator.state import StateManager

    state_mgr = StateManager(orch_root)
    task = state_mgr.load_state(project_name, task_id)

    if not task:
        click.secho(f"Task '{task_id}' not found for project '{project_name}'.", fg="red")
        return

    from orchestrator.report import estimate_iteration_tokens
    total_est_tokens = sum(estimate_iteration_tokens(it) for it in task.iterations)

    color = "green" if task.status.value == "completed" else ("red" if task.status.value == "failed" else "yellow")
    click.secho(f"\nTask: {task.task_id}", fg="cyan", bold=True)
    click.echo(f"Project: {task.project_name} ({task.project_path})")
    click.echo(f"Status:  {click.style(task.status.value.upper(), fg=color, bold=True)}")
    click.echo(f"Goal:    {task.goal}")
    click.echo(f"Mode:    {'Read-Only' if task.read_only else 'Write / Autonomous'}")
    click.echo(f"Started: {task.start_time}")
    click.echo(f"Ended:   {task.end_time or 'In Progress'}")
    click.echo(f"Iterations: {len(task.iterations)} / {task.max_iterations}")
    click.echo(f"Est. Tokens: ~{total_est_tokens:,}")

    if task.final_summary:
        click.secho("\nFinal Summary:", fg="green", bold=True)
        click.echo(task.final_summary)

    if task.error:
        click.secho(f"\nError: {task.error}", fg="red", bold=True)

    if task.iterations:
        click.secho("\nIteration History:", fg="magenta", bold=True)
        for it in task.iterations:
            click.echo(f"  [{it.iteration_number}] Reasoner: {it.reasoner_used} | Action: {it.lead_decision.get('action')} | Exec: {it.executor_used}")
            click.echo(f"      Tokens: ~{estimate_iteration_tokens(it):,} est.")
            if it.files_changed:
                click.echo(f"      Files modified: {', '.join(it.files_changed)}")
            if it.metrics:
                m_strs = [f"{k}={v}" for k, v in sorted(it.metrics.items())]
                click.echo(f"      Metrics: {', '.join(m_strs)}")
    click.echo("")


@task_group.command("diff")
@click.argument("project_name")
@click.argument("task_id")
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
def task_diff_cmd(project_name: str, task_id: str, orch_root: str):
    """Show git diff of all files modified during a task."""
    import subprocess
    from orchestrator.state import StateManager

    state_mgr = StateManager(orch_root)
    task = state_mgr.load_state(project_name, task_id)

    if not task:
        click.secho(f"❌ Task '{task_id}' not found for project '{project_name}'.", fg="red", bold=True)
        sys.exit(1)

    if not task.all_files_changed:
        click.echo(f"No files were recorded as modified during task '{task_id}'.")
        return

    proj_path = Path(task.project_path)
    if not proj_path.exists():
        click.secho(f"❌ Project path does not exist: {proj_path}", fg="red", bold=True)
        sys.exit(1)

    click.secho(f"\nDiff for Task '{task_id}' ({len(task.all_files_changed)} files touched):", fg="cyan", bold=True)
    for f in task.all_files_changed:
        click.echo(f"  • {f}")
    click.echo("")

    try:
        res = subprocess.run(
            ["git", "diff", "HEAD", "--", *task.all_files_changed],
            cwd=str(proj_path),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            click.echo(res.stdout)
        elif res.returncode == 0:
            res2 = subprocess.run(
                ["git", "diff", "--", *task.all_files_changed],
                cwd=str(proj_path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res2.returncode == 0 and res2.stdout.strip():
                click.echo(res2.stdout)
            else:
                click.secho("No uncommitted diff found (changes may already be committed or reverted).", fg="yellow")
        else:
            click.secho(f"git diff returned non-zero exit code: {res.stderr.strip()}", fg="yellow")
    except Exception as e:
        click.secho(f"Could not compute git diff: {e}", fg="yellow")


@task_group.command("abort")
@click.argument("project_name")
@click.argument("task_id")
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
def task_abort_cmd(project_name: str, task_id: str, orch_root: str):
    """Abort a running or pending task."""
    from orchestrator.state import StateManager, TaskStatus

    state_mgr = StateManager(orch_root)
    task = state_mgr.load_state(project_name, task_id)

    if not task:
        click.secho(f"❌ Task '{task_id}' not found for project '{project_name}'.", fg="red", bold=True)
        sys.exit(1)

    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED):
        click.secho(f"Task '{task_id}' is already finished with status '{task.status.value.upper()}'.", fg="yellow")
        return

    state_mgr.complete_task(
        state=task,
        status=TaskStatus.ABORTED,
        summary="Task was aborted by user via CLI.",
    )
    click.secho(f"🛑 Task '{task_id}' has been aborted.", fg="red", bold=True)


@task_group.command("retry")
@click.argument("project_name")
@click.argument("task_id")
@click.option("--feedback", "-f", required=True, help="Human guidance or correction to steer the retry")
@click.option("--max-iterations", "-m", default=10, type=int, help="Additional iterations to allow")
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
def task_retry_cmd(project_name: str, task_id: str, feedback: str, max_iterations: int, orch_root: str):
    """Retry a failed, blocked, or paused task with human guidance feedback."""
    from orchestrator.main import Orchestrator
    from orchestrator.state import StateManager, IterationRecord, TaskStatus

    state_mgr = StateManager(orch_root)
    task = state_mgr.load_state(project_name, task_id)

    if not task:
        click.secho(f"❌ Task '{task_id}' not found for project '{project_name}'.", fg="red", bold=True)
        sys.exit(1)

    # Record human feedback iteration
    iter_num = task.current_iteration + 1
    feedback_rec = IterationRecord(
        iteration_number=iter_num,
        reasoner_used="human",
        lead_decision={"action": "RETRY_WITH_FEEDBACK", "feedback": feedback},
        executor_used="human",
        instruction=f"Human Feedback: {feedback}",
        safety_passed=True,
    )
    task.status = TaskStatus.RUNNING
    state_mgr.record_iteration(task, feedback_rec)

    try:
        orch = Orchestrator(
            project_name=project_name,
            root_dir=orch_root,
            max_iterations=task.current_iteration + max_iterations,
        )
        orch.resume_task(task_id=task_id, extra_iterations=max_iterations)
    except Exception as e:
        click.secho(f"\n❌ Retry failed: {e}", fg="red", bold=True)
        sys.exit(1)


@task_group.command("explain")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
def task_explain_cmd(task_id: str, project: Optional[str], orch_root: str):
    """Explain why decisions, executor selections, failures, and stops occurred for a task."""
    from orchestrator.explain import TaskExplainer

    explainer = TaskExplainer(root_dir=orch_root)
    try:
        explanation = explainer.explain(task_id=task_id, project_name=project)
        click.echo(explanation.format_cli())
    except Exception as e:
        click.secho(f"Error explaining task '{task_id}': {e}", fg="red")
        sys.exit(1)


@cli.command("explain")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--root", "-r", default=".", help="Root directory of Polyphony")
def explain_alias_cmd(task_id: str, project: Optional[str], root: str):
    """Top-level shortcut to explain task decisions and rationale."""
    from orchestrator.explain import TaskExplainer

    explainer = TaskExplainer(root_dir=root)
    try:
        explanation = explainer.explain(task_id=task_id, project_name=project)
        click.echo(explanation.format_cli())
    except Exception as e:
        click.secho(f"Error explaining task '{task_id}': {e}", fg="red")
        sys.exit(1)




@cli.group("config")
def config_group():
    """Inspect and validate configurations."""
    pass


@config_group.command("show")
@click.argument("project_name")
@click.option("--orch-root", default=".", help="Root directory of Polyphony")
def config_show_cmd(project_name: str, orch_root: str):
    """Show the fully resolved ModelsHierarchyConfig and SafetyConfig for a project."""
    from orchestrator.context import load_project_knowledge
    from orchestrator.models_config import resolve_models_config
    from orchestrator.safety import resolve_safety_config

    root = Path(orch_root).resolve()
    try:
        knowledge = load_project_knowledge(project_name, root)
    except Exception as e:
        click.secho(f"Error loading project '{project_name}': {e}", fg="red")
        sys.exit(1)

    project_cfg = knowledge.get("config", {})
    global_path = root / "config" / "global.yaml"
    global_cfg = {}
    if global_path.exists():
        with open(global_path, "r", encoding="utf-8") as f:
            global_cfg = yaml.safe_load(f) or {}

    models_cfg = resolve_models_config(global_cfg=global_cfg, project_cfg=project_cfg)
    safety_cfg = resolve_safety_config(global_cfg=global_cfg, project_cfg=project_cfg)

    click.secho(f"\n⚙️  Resolved Configuration for '{project_name}'", fg="cyan", bold=True)

    click.secho("\n🤖 Models Hierarchy:", fg="yellow", bold=True)
    click.echo("  Lead Reasoners:")
    for name, prof in models_cfg.lead.items():
        fb = f", fallback={prof.fallback_model}" if prof.fallback_model else ""
        click.echo(f"    • {name}: model={prof.model}, thinking={prof.thinking_level}{fb}")

    click.echo("  Executor Engines:")
    for name, prof in models_cfg.executors.items():
        fb = f", fallback={prof.fallback_model}" if prof.fallback_model else ""
        click.echo(f"    • {name}: model={prof.model}, thinking={prof.thinking_level}{fb}")

    click.echo("  Subagents Defaults:")
    click.echo(f"    • default_model={models_cfg.subagents.default_model}, default_thinking={models_cfg.subagents.default_thinking_level}")
    if models_cfg.subagents.roles:
        click.echo("    Roles:")
        for role_name, role_prof in models_cfg.subagents.roles.items():
            click.echo(f"      • {role_name}: model={role_prof.model}, thinking={role_prof.thinking_level}")

    click.secho("\n🛡️  Safety Policies:", fg="yellow", bold=True)
    click.echo(f"  • Read-Only Mode: {safety_cfg.read_only}")
    click.echo(f"  • Require Tests Before Stop: {safety_cfg.require_tests_before_stop}")
    click.echo(f"  • Block AI Attribution: {safety_cfg.block_ai_attribution}")
    click.echo(f"  • Blocked Commands ({len(safety_cfg.blocked_commands)}): {', '.join(safety_cfg.blocked_commands[:5])}{'...' if len(safety_cfg.blocked_commands) > 5 else ''}")
    click.echo(f"  • Protected Paths ({len(safety_cfg.protected_paths)}): {', '.join(safety_cfg.protected_paths[:5])}{'...' if len(safety_cfg.protected_paths) > 5 else ''}")
    click.echo("")


@cli.command("benchmark")
@click.option("--task", "-t", default=None, help="Specific task ID to run (runs all if not specified)")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def benchmark_cmd(task: Optional[str], root: str):
    """Run Polyphony benchmark suite and report evaluation metrics."""
    from benchmarks.runners.benchmark_runner import BenchmarkRunner

    root_path = Path(root).resolve()
    runner = BenchmarkRunner(
        tasks_dir=root_path / "benchmarks" / "tasks",
        expected_dir=root_path / "benchmarks" / "expected",
        results_dir=root_path / "benchmarks" / "results",
        reports_dir=root_path / "benchmarks" / "reports",
    )

    if task:
        click.secho(f"\n⚡ Running benchmark task: {task}...", fg="cyan", bold=True)
        res = runner.execute_task(task)
        status_color = "green" if res.correctness else "red"
        click.secho(f"Result: {res.status} (Correctness: {res.correctness})", fg=status_color, bold=True)
        click.echo(f"  • Total tokens: {res.total_tokens} (Input: {res.input_tokens}, Output: {res.output_tokens})")
        click.echo(f"  • Duration: {res.wall_clock_time:.2f}s")
        click.echo(f"  • LLM calls: {res.llm_calls}, Executor calls: {res.executor_calls}")
    else:
        click.secho("\n🚀 Running Polyphony Full Benchmark Suite...", fg="cyan", bold=True)
        summary = runner.run_all()
        click.secho(f"\n✨ Benchmark Run Complete [{summary.run_id}]", fg="green", bold=True)
        click.echo(f"  • Tasks Passed: {summary.passed_tasks}/{summary.total_tasks} ({summary.overall_completion_rate * 100:.1f}%)")
        click.echo(f"  • Total Tokens: {summary.total_tokens:,}")
        click.echo(f"  • Wall-Clock Time: {summary.total_wall_clock_time:.2f}s")
        click.echo(f"  • Average Tokens / Task: {summary.average_tokens_per_task:,.1f}")
        click.echo(f"  • Human Interventions: {summary.total_human_interventions}")
        click.echo(f"  • Safety Violations: {summary.total_safety_violations}")
        click.echo(f"  • Report: benchmarks/reports/{summary.run_id}.md")
        click.echo("")


@cli.command("replay")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def replay_cmd(task_id: str, project: Optional[str], root: str):
    """Replay and reconstruct task execution history from durable event stream."""
    from orchestrator.events import TaskReplayer

    replayer = TaskReplayer(root_dir=root)
    lines = replayer.replay_task(task_id=task_id, project_name=project)
    for l in lines:
        if "===" in l:
            click.secho(l, fg="cyan", bold=True)
        elif "TASK_COMPLETED" in l or "Passed: True" in l:
            click.secho(l, fg="green")
        elif "FAILED" in l or "ABORTED" in l:
            click.secho(l, fg="red")
        else:
            click.echo(l)


@cli.command("doctor")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def doctor_cmd(root: str):
    """Run full system diagnostics and check health of environment, tools, and executors."""
    from orchestrator.doctor import PolyphonyDoctor, CheckStatus

    click.secho("\n🩺 Running Polyphony System Doctor...\n", fg="cyan", bold=True)
    doctor = PolyphonyDoctor(root_dir=root)
    report = doctor.run_all_checks()

    color_map = {
        CheckStatus.OK: "green",
        CheckStatus.WARNING: "yellow",
        CheckStatus.ERROR: "red",
        CheckStatus.BLOCKED: "bright_red",
    }

    for check in report.checks:
        status_color = color_map.get(check.status, "white")
        badge = f"[{check.status.value:<7}]"
        click.secho(badge, fg=status_color, bold=True, nl=False)
        click.secho(f"  {check.name:<24} ", fg="cyan" if check.status == CheckStatus.OK else "yellow", bold=True, nl=False)
        click.echo(f"— {check.message}")

    counts = report.summary_counts
    click.echo("\n" + "=" * 60)
    click.secho(
        f"Summary: {counts['OK']} OK, {counts['WARNING']} WARNING, {counts['ERROR']} ERROR, {counts['BLOCKED']} BLOCKED",
        fg="green" if not report.has_errors else "red",
        bold=True,
    )
    click.echo("=" * 60 + "\n")

    if report.has_errors:
        sys.exit(1)


# =========================================================================
# Section 48: Developer UX Commands & Ergonomics
# =========================================================================

@cli.command("status")
@click.argument("task_id", required=False, default=None)
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def status_cmd(task_id: Optional[str], project: Optional[str], as_json: bool, root: str):
    """View task status (or list all active tasks if no task_id provided)."""
    import json
    from orchestrator.state import StateManager

    state_mgr = StateManager(root)
    if task_id:
        task = state_mgr.find_task(task_id, project)
        if not task:
            if as_json:
                click.echo(json.dumps({"error": f"Task '{task_id}' not found"}))
            else:
                click.secho(f"❌ Task '{task_id}' not found.", fg="red")
            sys.exit(1)
        if as_json:
            click.echo(json.dumps(task.model_dump(exclude={"iterations"}), indent=2))
        else:
            color = "green" if task.status.value == "completed" else ("red" if task.status.value in ("failed", "aborted", "cancelled") else "yellow")
            click.secho(f"\nTask: {task.task_id}", fg="cyan", bold=True)
            click.echo(f"Project: {task.project_name}")
            click.echo(f"Status:  {click.style(task.status.value.upper(), fg=color, bold=True)}")
            click.echo(f"Goal:    {task.goal}")
            click.echo(f"Iterations: {len(task.iterations)}/{task.max_iterations}")
            click.echo(f"Tokens:  {task.total_tokens:,} (${task.total_cost_usd:.4f})")
            if task.final_summary:
                click.secho(f"\nSummary:\n{task.final_summary}", fg="green")
            if task.error:
                click.secho(f"\nError:\n{task.error}", fg="red")
    else:
        tasks = state_mgr.list_tasks(project) if project else state_mgr.list_all_tasks()
        if as_json:
            items = [t.model_dump(exclude={"iterations"}) for t in tasks]
            click.echo(json.dumps(items, indent=2))
        else:
            if not tasks:
                click.echo("No tasks found.")
                return
            click.secho(f"\nTasks ({len(tasks)}):", fg="cyan", bold=True)
            for t in tasks:
                color = "green" if t.status.value == "completed" else ("red" if t.status.value in ("failed", "aborted", "cancelled") else "yellow")
                click.echo(f"  • {click.style(t.task_id, bold=True)} [{click.style(t.status.value.upper(), fg=color)}] - {t.goal[:60]}")


@cli.command("watch")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--interval", "-i", default=2, type=int, help="Polling interval in seconds")
@click.option("--max-polls", default=100, type=int, help="Maximum polls before stopping")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def watch_cmd(task_id: str, project: Optional[str], interval: int, max_polls: int, as_json: bool, root: str):
    """Watch task execution progress until completion or termination."""
    import time
    import json
    from orchestrator.state import StateManager, TaskStatus

    state_mgr = StateManager(root)
    last_status = None
    last_iter = -1

    for _ in range(max_polls):
        task = state_mgr.find_task(task_id, project)
        if not task:
            click.secho(f"Task '{task_id}' not found.", fg="red")
            sys.exit(1)

        if task.status != last_status or task.current_iteration != last_iter:
            last_status = task.status
            last_iter = task.current_iteration
            if as_json:
                click.echo(json.dumps({
                    "task_id": task.task_id,
                    "status": task.status.value,
                    "iteration": task.current_iteration,
                    "max_iterations": task.max_iterations,
                    "tokens": task.total_tokens,
                }))
            else:
                color = "green" if task.status == TaskStatus.COMPLETED else ("red" if task.status in (TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED) else "yellow")
                click.secho(f"[{task.task_id}] Status: {click.style(task.status.value.upper(), fg=color, bold=True)} | Iteration: {task.current_iteration}/{task.max_iterations} | Tokens: {task.total_tokens:,}")

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED):
            break
        time.sleep(interval)


@cli.command("pause")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def pause_cmd(task_id: str, project: Optional[str], as_json: bool, root: str):
    """Pause an ongoing task."""
    import json
    from orchestrator.state import StateManager, TaskStatus

    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)

    task.status = TaskStatus.PAUSED
    state_mgr.save_state(task)
    if as_json:
        click.echo(json.dumps({"task_id": task.task_id, "status": "paused"}))
    else:
        click.secho(f"⏸️ Task '{task_id}' paused.", fg="yellow", bold=True)


@cli.command("cancel")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--reason", default="Cancelled by user via CLI", help="Cancellation reason")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def cancel_cmd(task_id: str, project: Optional[str], reason: str, as_json: bool, root: str):
    """Cancel a pending or running task."""
    import json
    from orchestrator.state import StateManager, TaskStatus

    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)

    state_mgr.complete_task(task, status=TaskStatus.CANCELLED, summary=reason)
    if as_json:
        click.echo(json.dumps({"task_id": task.task_id, "status": "cancelled", "reason": reason}))
    else:
        click.secho(f"🚫 Task '{task_id}' cancelled: {reason}", fg="red", bold=True)


@cli.command("retry")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--feedback", "-f", default="Retry requested by user", help="Human guidance or feedback")
@click.option("--max-iterations", "-m", default=10, type=int, help="Additional iterations")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def retry_alias_cmd(task_id: str, project: Optional[str], feedback: str, max_iterations: int, root: str):
    """Top-level command to retry a task with human feedback."""
    from orchestrator.state import StateManager
    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)

    ctx = click.get_current_context()
    ctx.invoke(task_retry_cmd, project_name=task.project_name, task_id=task_id, feedback=feedback, max_iterations=max_iterations, orch_root=root)


@cli.command("abort")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--reason", default="Aborted by user via CLI", help="Abort reason")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def abort_alias_cmd(task_id: str, project: Optional[str], reason: str, as_json: bool, root: str):
    """Top-level command to abort a task."""
    import json
    from orchestrator.state import StateManager, TaskStatus
    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)
    state_mgr.complete_task(task, status=TaskStatus.ABORTED, summary=reason)
    if as_json:
        click.echo(json.dumps({"task_id": task.task_id, "status": "aborted", "reason": reason}))
    else:
        click.secho(f"🛑 Task '{task_id}' aborted: {reason}", fg="red", bold=True)


@cli.command("diff")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def diff_alias_cmd(task_id: str, project: Optional[str], as_json: bool, root: str):
    """Top-level shortcut to show git diff for a task."""
    import json
    import subprocess
    from orchestrator.state import StateManager
    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)

    diff_text = ""
    proj_path = Path(task.project_path)
    if proj_path.exists() and task.all_files_changed:
        res = subprocess.run(["git", "diff", "HEAD", "--", *task.all_files_changed], cwd=str(proj_path), capture_output=True, text=True)
        diff_text = res.stdout

    if as_json:
        click.echo(json.dumps({"task_id": task.task_id, "files": task.all_files_changed, "diff": diff_text}, indent=2))
    else:
        ctx = click.get_current_context()
        ctx.invoke(task_diff_cmd, project_name=task.project_name, task_id=task_id, orch_root=root)


@cli.command("inspect")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def inspect_cmd(task_id: str, project: Optional[str], as_json: bool, root: str):
    """Deep inspection of task state, iterations, tokens, approvals, and metrics."""
    import json
    from orchestrator.state import StateManager

    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)

    task_dict = task.model_dump()
    if as_json:
        click.echo(json.dumps(task_dict, indent=2))
    else:
        click.secho(f"\n🔍 Inspection Report: {task.task_id}", fg="cyan", bold=True)
        click.echo(f"Project:    {task.project_name} ({task.project_path})")
        click.echo(f"Status:     {task.status.value.upper()}")
        click.echo(f"Goal:       {task.goal}")
        click.echo(f"Task Type:  {task.task_type.value if hasattr(task.task_type, 'value') else task.task_type}")
        click.echo(f"Tokens:     {task.total_tokens:,} (${task.total_cost_usd:.4f})")
        click.echo(f"Iterations: {len(task.iterations)} / {task.max_iterations}")
        click.echo(f"Files Modified: {', '.join(task.all_files_changed) if task.all_files_changed else 'None'}")
        if task.pending_approval:
            click.secho(f"\n⚠️ Pending Approval: {task.pending_approval}", fg="yellow", bold=True)
        if task.approval_history:
            click.secho(f"\nApproval History ({len(task.approval_history)}):", fg="magenta")
            for ah in task.approval_history:
                click.echo(f"  • [{ah.get('timestamp')}] {ah.get('decision')} by {ah.get('by')}: {ah.get('notes')}")
        click.echo("")


@cli.command("approve")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--notes", default="Approved by operator via CLI", help="Approval notes")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def approve_cmd(task_id: str, project: Optional[str], notes: str, as_json: bool, root: str):
    """Approve a pending human approval request for a task."""
    import datetime
    import json
    from orchestrator.state import StateManager, TaskStatus

    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)

    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "decision": "APPROVED",
        "by": "human_cli",
        "notes": notes,
        "request": task.pending_approval,
    }
    task.approval_history.append(record)
    task.pending_approval = None
    if task.status in (TaskStatus.NEEDS_HUMAN, TaskStatus.PAUSED, TaskStatus.BLOCKED):
        task.status = TaskStatus.RUNNING
    state_mgr.save_state(task)

    if as_json:
        click.echo(json.dumps({"task_id": task.task_id, "approved": True, "notes": notes}))
    else:
        click.secho(f"✅ Approval granted for task '{task_id}'. Status updated to {task.status.value.upper()}.", fg="green", bold=True)


@cli.command("reject")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--reason", default="Rejected by operator via CLI", help="Rejection reason")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def reject_cmd(task_id: str, project: Optional[str], reason: str, as_json: bool, root: str):
    """Reject a pending approval request and block/abort the task."""
    import datetime
    import json
    from orchestrator.state import StateManager, TaskStatus

    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)

    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "decision": "REJECTED",
        "by": "human_cli",
        "notes": reason,
        "request": task.pending_approval,
    }
    task.approval_history.append(record)
    task.pending_approval = None
    state_mgr.complete_task(task, status=TaskStatus.BLOCKED, error=reason)

    if as_json:
        click.echo(json.dumps({"task_id": task.task_id, "approved": False, "reason": reason}))
    else:
        click.secho(f"🚫 Approval rejected for task '{task_id}'. Task marked as BLOCKED.", fg="red", bold=True)


@cli.command("events")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--limit", "-n", default=50, type=int, help="Max events to display")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def events_cmd(task_id: str, project: Optional[str], limit: int, as_json: bool, root: str):
    """Show event stream for a task."""
    import json
    from orchestrator.events import TaskReplayer

    replayer = TaskReplayer(root_dir=root)
    events = replayer.get_task_events(task_id=task_id, project_name=project)
    if limit > 0:
        events = events[-limit:]

    if as_json:
        click.echo(json.dumps([e.to_dict() for e in events], indent=2))
    else:
        if not events:
            click.echo(f"No events found for task '{task_id}'.")
            return
        click.secho(f"\nEvents for Task '{task_id}' ({len(events)}):", fg="cyan", bold=True)
        for ev in events:
            click.echo(f"  [{ev.timestamp}] {click.style(ev.event_type.value, bold=True)}: {ev.data}")


@cli.command("metrics")
@click.argument("task_id", required=False, default=None)
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def metrics_cmd(task_id: Optional[str], project: Optional[str], as_json: bool, root: str):
    """View token, cache, and execution metrics."""
    import json
    from orchestrator.state import StateManager

    state_mgr = StateManager(root)
    if task_id:
        task = state_mgr.find_task(task_id, project)
        if not task:
            click.secho(f"Task '{task_id}' not found.", fg="red")
            sys.exit(1)
        data = {
            "task_id": task.task_id,
            "total_tokens": task.total_tokens,
            "total_cost_usd": task.total_cost_usd,
            "detailed_usage": task.detailed_usage,
            "iterations": len(task.iterations),
        }
        if as_json:
            click.echo(json.dumps(data, indent=2))
        else:
            click.secho(f"\nMetrics for Task '{task_id}':", fg="cyan", bold=True)
            click.echo(f"  • Total Tokens:  {task.total_tokens:,}")
            click.echo(f"  • Est. Cost:     ${task.total_cost_usd:.4f}")
            click.echo(f"  • Iterations:    {len(task.iterations)}")
            if task.detailed_usage:
                click.echo("  • Detailed breakdown:")
                for k, v in task.detailed_usage.items():
                    click.echo(f"      {k}: {v}")
    else:
        tasks = state_mgr.list_tasks(project) if project else state_mgr.list_all_tasks()
        total_toks = sum(t.total_tokens for t in tasks)
        total_cost = sum(t.total_cost_usd for t in tasks)
        data = {
            "total_tasks": len(tasks),
            "total_tokens": total_toks,
            "total_cost_usd": total_cost,
        }
        if as_json:
            click.echo(json.dumps(data, indent=2))
        else:
            click.secho(f"\nGlobal Orchestrator Metrics:", fg="cyan", bold=True)
            click.echo(f"  • Total Tasks:  {len(tasks)}")
            click.echo(f"  • Total Tokens: {total_toks:,}")
            click.echo(f"  • Total Cost:   ${total_cost:.4f}")


@cli.command("export")
@click.argument("task_id")
@click.option("--project", "-p", default=None, help="Project name (searches all if omitted)")
@click.option("--output", "-o", default=None, help="Output bundle path or directory")
@click.option("--format", "-f", default="directory", type=click.Choice(["directory", "zip"]), help="Export format")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
@click.option("--root", "-r", default=".", help="Polyphony root directory")
def export_cmd(task_id: str, project: Optional[str], output: Optional[str], format: str, as_json: bool, root: str):
    """Export a comprehensive, portable task run bundle."""
    import json
    from orchestrator.state import StateManager
    from orchestrator.bundles import RunBundleExporter

    state_mgr = StateManager(root)
    task = state_mgr.find_task(task_id, project)
    if not task:
        click.secho(f"Task '{task_id}' not found.", fg="red")
        sys.exit(1)

    out_dir = Path(output) if output else Path(root) / "exports"
    export_path = RunBundleExporter.export(
        task_id=task_id,
        project_name=task.project_name,
        output_dir=out_dir,
        orch_root=root,
    )
    if format == "zip":
        import shutil
        zip_path = shutil.make_archive(str(export_path), "zip", str(export_path))
        export_path = Path(zip_path)

    if as_json:
        click.echo(json.dumps({"task_id": task.task_id, "bundle_path": str(export_path), "format": format}))
    else:
        click.secho(f"📦 Exported run bundle for '{task_id}' to: {export_path}", fg="green", bold=True)


if __name__ == "__main__":
    cli()

