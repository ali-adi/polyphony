"""Tests for Background Automation (Section 49) and Project-Level Missions (Section 50)."""

import pytest
from pathlib import Path

from orchestrator.automation import (
    BackgroundAutomationManager,
    BackgroundJobType,
)
from orchestrator.missions import (
    Mission,
    MissionCoordinator,
    MissionDecomposer,
    MissionStatus,
    StageStatus,
)
from orchestrator.policy import HumanApprovalPolicyEngine, PolicyAction, RiskLevel


def test_background_automation_audits_and_policy(tmp_path: Path):
    proj_dir = tmp_path / "test_proj"
    proj_dir.mkdir(parents=True, exist_ok=True)

    manager = BackgroundAutomationManager(
        project_name="test_proj",
        project_path=proj_dir,
    )

    # 1. Dependency audit without manifests
    report_dep = manager.run_dependency_audit()
    assert report_dep.job_type == BackgroundJobType.DEPENDENCY_AUDIT
    assert any(f.severity == "WARNING" for f in report_dep.findings)

    # Add requirements.txt and re-run
    (proj_dir / "requirements.txt").write_text("pytest>=8.0\n", encoding="utf-8")
    report_dep2 = manager.run_dependency_audit()
    assert any(f.severity == "INFO" for f in report_dep2.findings)

    # 2. Doc freshness audit without README
    report_doc = manager.run_doc_freshness()
    assert any(f.severity == "WARNING" for f in report_doc.findings)

    # Add README and re-run
    (proj_dir / "README.md").write_text("# Test Project\n\nThis is a complete documentation file exceeding fifty bytes.\n", encoding="utf-8")
    report_doc2 = manager.run_doc_freshness()
    assert any(f.severity == "INFO" for f in report_doc2.findings)

    # 3. Policy controls: background jobs cannot mutate without passing policy
    allowed, msg = manager.request_background_mutation(
        action_description="write file",
        files_to_modify=["critical/auth.py"],
        patch_content="new code",
    )
    # By default, writing files is MEDIUM risk which passes or requires ask
    # Let's test with a critical operation
    allowed_crit, msg_crit = manager.request_background_mutation(
        action_description="deploy prod and credential change",
        files_to_modify=["prod/keys.env"],
        patch_content="SECRET=123",
    )
    assert not allowed_crit
    assert "Blocked by policy" in msg_crit or "Requires human approval" in msg_crit


def test_mission_decomposition():
    mission = MissionDecomposer.decompose(
        title="Make ICD-10 coding pipeline production-ready",
        project_name="icd10_pipeline",
        global_budget=200000,
    )

    assert mission.title == "Make ICD-10 coding pipeline production-ready"
    assert mission.project_name == "icd10_pipeline"
    assert mission.global_token_budget == 200000
    assert len(mission.stages) == 6

    # Verify stage ordering and dependencies
    stage_map = {s.stage_id: s for s in mission.stages}
    assert "architecture_audit" in stage_map
    assert "security_audit" in stage_map
    assert "performance_benchmark" in stage_map
    assert "implementation" in stage_map
    assert "tests" in stage_map
    assert "deployment_readiness_audit" in stage_map

    # architecture_audit should be ready initially
    assert stage_map["architecture_audit"].status == StageStatus.READY
    # subsequent stages should be pending
    assert stage_map["security_audit"].status == StageStatus.PENDING
    assert stage_map["implementation"].depends_on == ["security_audit", "performance_benchmark"]


def test_mission_coordinator_lifecycle_and_budget(tmp_path: Path):
    mission = MissionDecomposer.decompose(
        title="Production Hardening",
        project_name="core_service",
        global_budget=50000,
    )

    # 1. Stage 1: architecture_audit
    ready_stages = MissionCoordinator.get_ready_stages(mission)
    assert len(ready_stages) == 1
    assert ready_stages[0].stage_id == "architecture_audit"

    MissionCoordinator.start_stage(mission, "architecture_audit", "task-101")
    assert mission.status == MissionStatus.RUNNING

    MissionCoordinator.complete_stage(
        mission=mission,
        stage_id="architecture_audit",
        tokens_used=10000,
        summary="Architecture reviewed and approved.",
        artifacts=["arch_spec.md"],
        shared_facts={"architecture_version": "2.0"},
    )

    assert mission.tokens_used == 10000
    assert mission.shared_memory["architecture_version"] == "2.0"

    # 2. Stages 2 & 3: security_audit and performance_benchmark should now be ready
    ready2 = MissionCoordinator.get_ready_stages(mission)
    ready_ids = {s.stage_id for s in ready2}
    assert ready_ids == {"security_audit", "performance_benchmark"}

    # Complete stage 2
    MissionCoordinator.complete_stage(
        mission=mission,
        stage_id="security_audit",
        tokens_used=8000,
        summary="Security audit passed zero vulns.",
    )

    # Complete stage 3
    MissionCoordinator.complete_stage(
        mission=mission,
        stage_id="performance_benchmark",
        tokens_used=12000,
        summary="Performance under 20ms p99.",
    )

    # 3. Stage 4: implementation should now be ready
    ready3 = MissionCoordinator.get_ready_stages(mission)
    assert [s.stage_id for s in ready3] == ["implementation"]

    MissionCoordinator.complete_stage(
        mission=mission,
        stage_id="implementation",
        tokens_used=10000,
        summary="Implementation finished.",
    )

    # 4. Stage 5: tests
    ready4 = MissionCoordinator.get_ready_stages(mission)
    assert [s.stage_id for s in ready4] == ["tests"]

    MissionCoordinator.complete_stage(
        mission=mission,
        stage_id="tests",
        tokens_used=5000,
        summary="All tests passed.",
    )

    # 5. Stage 6: deployment_readiness_audit
    ready5 = MissionCoordinator.get_ready_stages(mission)
    assert [s.stage_id for s in ready5] == ["deployment_readiness_audit"]

    MissionCoordinator.complete_stage(
        mission=mission,
        stage_id="deployment_readiness_audit",
        tokens_used=4000,
        summary="Deployment signoff granted.",
    )

    # All stages completed!
    assert mission.status == MissionStatus.COMPLETED
    assert mission.tokens_used == 49000

    # Check budget
    ok, budget_msg = MissionCoordinator.check_budget_limits(mission)
    assert ok
    assert "1,000 tokens remaining" in budget_msg

    # Progress reporting
    progress = MissionCoordinator.calculate_progress(mission)
    assert progress["progress_percent"] == 100.0
    assert progress["completed_stages"] == 6

    # Test save and reload
    save_path = MissionCoordinator.save_mission(mission, tmp_path)
    assert save_path.exists()

    loaded = MissionCoordinator.load_mission(tmp_path, "core_service", mission.mission_id)
    assert loaded is not None
    assert loaded.status == MissionStatus.COMPLETED
    assert loaded.tokens_used == 49000
    assert loaded.shared_memory["architecture_version"] == "2.0"
