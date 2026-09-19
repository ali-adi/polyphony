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


if __name__ == "__main__":
    cli()
