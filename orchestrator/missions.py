"""Project-Level Missions coordinator and stage decomposition (Section 50).

Supports high-level missions that decompose into sequential and dependent child tasks:
architecture audit
       ↓
security audit
       ↓
performance benchmark
       ↓
implementation
       ↓
tests
       ↓
deployment-readiness audit

Coordinates:
- Global token budget
- Deadlines
- Safety policy
- Success criteria
- Child tasks
- Shared memory across child tasks
- Progress tracking
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MissionStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class MissionStage:
    stage_id: str
    name: str
    order: int
    depends_on: List[str] = field(default_factory=list)
    status: StageStatus = StageStatus.PENDING
    task_id: Optional[str] = None
    tokens_used: int = 0
    summary: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class Mission:
    mission_id: str
    title: str
    project_name: str
    global_token_budget: int = 250000
    tokens_used: int = 0
    deadline: Optional[str] = None
    safety_policy: Dict[str, Any] = field(default_factory=dict)
    success_criteria: List[str] = field(default_factory=list)
    stages: List[MissionStage] = field(default_factory=list)
    shared_memory: Dict[str, Any] = field(default_factory=dict)
    status: MissionStatus = MissionStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        for s in d["stages"]:
            s["status"] = s["status"].value if hasattr(s["status"], "value") else str(s["status"])
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Mission:
        stages_raw = data.get("stages", [])
        stages = []
        for s in stages_raw:
            st = s.copy()
            if isinstance(st.get("status"), str):
                st["status"] = StageStatus(st["status"])
            stages.append(MissionStage(**st))

        status = MissionStatus(data.get("status", "PENDING"))
        return cls(
            mission_id=data["mission_id"],
            title=data["title"],
            project_name=data["project_name"],
            global_token_budget=data.get("global_token_budget", 250000),
            tokens_used=data.get("tokens_used", 0),
            deadline=data.get("deadline"),
            safety_policy=data.get("safety_policy", {}),
            success_criteria=data.get("success_criteria", []),
            stages=stages,
            shared_memory=data.get("shared_memory", {}),
            status=status,
            created_at=data.get("created_at", datetime.datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.datetime.now().isoformat()),
        )


class MissionDecomposer:
    """Decomposes high-level engineering goals into standard Mission stages (Section 50)."""

    STANDARD_STAGES = [
        ("architecture_audit", "architecture audit", []),
        ("security_audit", "security audit", ["architecture_audit"]),
        ("performance_benchmark", "performance benchmark", ["architecture_audit"]),
        ("implementation", "implementation", ["security_audit", "performance_benchmark"]),
        ("tests", "tests", ["implementation"]),
        ("deployment_readiness_audit", "deployment-readiness audit", ["tests"]),
    ]

    @classmethod
    def decompose(
        cls,
        title: str,
        project_name: str,
        global_budget: int = 250000,
        deadline: Optional[str] = None,
        safety_policy: Optional[Dict[str, Any]] = None,
        success_criteria: Optional[List[str]] = None,
    ) -> Mission:
        mission_id = f"mission-{int(datetime.datetime.now().timestamp())}"
        stages = []

        for idx, (s_id, s_name, deps) in enumerate(cls.STANDARD_STAGES, 1):
            # The first stage has no dependencies and is immediately READY
            initial_status = StageStatus.READY if not deps else StageStatus.PENDING
            stages.append(
                MissionStage(
                    stage_id=s_id,
                    name=s_name,
                    order=idx,
                    depends_on=deps,
                    status=initial_status,
                )
            )

        criteria = success_criteria or [
            "Pass architecture audit",
            "Pass security audit with zero critical vulnerabilities",
            "Performance benchmarks meet latency threshold",
            "Clean test suite pass (100%)",
            "Deployment-readiness signoff",
        ]

        return Mission(
            mission_id=mission_id,
            title=title,
            project_name=project_name,
            global_token_budget=global_budget,
            tokens_used=0,
            deadline=deadline,
            safety_policy=safety_policy or {"read_only_until_implementation": True},
            success_criteria=criteria,
            stages=stages,
            status=MissionStatus.PENDING,
        )


class MissionCoordinator:
    """Orchestrates mission execution, tracking stage dependencies, shared memory, and global budget."""

    @staticmethod
    def get_ready_stages(mission: Mission) -> List[MissionStage]:
        """Returns stages whose dependencies are all completed and are ready to execute."""
        completed_stage_ids = {
            s.stage_id for s in mission.stages if s.status == StageStatus.COMPLETED
        }
        ready: List[MissionStage] = []
        for s in mission.stages:
            if s.status == StageStatus.PENDING:
                if all(dep in completed_stage_ids for dep in s.depends_on):
                    s.status = StageStatus.READY
                    ready.append(s)
            elif s.status == StageStatus.READY:
                ready.append(s)
        return ready

    @staticmethod
    def start_stage(mission: Mission, stage_id: str, task_id: str) -> None:
        for s in mission.stages:
            if s.stage_id == stage_id:
                s.status = StageStatus.RUNNING
                s.task_id = task_id
                mission.status = MissionStatus.RUNNING
                mission.updated_at = datetime.datetime.now().isoformat()
                return
        raise ValueError(f"Stage '{stage_id}' not found in mission '{mission.mission_id}'")

    @staticmethod
    def complete_stage(
        mission: Mission,
        stage_id: str,
        tokens_used: int,
        summary: str,
        artifacts: Optional[List[str]] = None,
        shared_facts: Optional[Dict[str, Any]] = None,
    ) -> None:
        target_stage: Optional[MissionStage] = None
        for s in mission.stages:
            if s.stage_id == stage_id:
                target_stage = s
                break

        if not target_stage:
            raise ValueError(f"Stage '{stage_id}' not found")

        target_stage.status = StageStatus.COMPLETED
        target_stage.tokens_used = tokens_used
        target_stage.summary = summary
        if artifacts:
            target_stage.artifacts.extend(artifacts)

        # Update mission global metrics
        mission.tokens_used += tokens_used
        if shared_facts:
            mission.shared_memory.update(shared_facts)

        mission.updated_at = datetime.datetime.now().isoformat()

        # Check if all stages completed
        if all(s.status == StageStatus.COMPLETED for s in mission.stages):
            mission.status = MissionStatus.COMPLETED
        else:
            # Refresh ready stages
            MissionCoordinator.get_ready_stages(mission)

    @staticmethod
    def fail_stage(mission: Mission, stage_id: str, error: str) -> None:
        for s in mission.stages:
            if s.stage_id == stage_id:
                s.status = StageStatus.FAILED
                s.error = error
                mission.status = MissionStatus.FAILED
                mission.updated_at = datetime.datetime.now().isoformat()
                return
        raise ValueError(f"Stage '{stage_id}' not found")

    @staticmethod
    def check_budget_limits(mission: Mission) -> Tuple[bool, str]:
        """Validates that the mission has not exceeded its global token budget."""
        if mission.tokens_used > mission.global_token_budget:
            return (
                False,
                f"Global budget exceeded: spent {mission.tokens_used:,} tokens (limit {mission.global_token_budget:,})",
            )
        remaining = mission.global_token_budget - mission.tokens_used
        return True, f"Budget compliant: {remaining:,} tokens remaining"

    @staticmethod
    def calculate_progress(mission: Mission) -> Dict[str, Any]:
        total_stages = len(mission.stages)
        completed = sum(1 for s in mission.stages if s.status == StageStatus.COMPLETED)
        pct = (completed / total_stages) * 100.0 if total_stages > 0 else 0.0

        return {
            "mission_id": mission.mission_id,
            "title": mission.title,
            "status": mission.status.value,
            "total_stages": total_stages,
            "completed_stages": completed,
            "progress_percent": round(pct, 1),
            "tokens_used": mission.tokens_used,
            "tokens_budget": mission.global_token_budget,
            "shared_memory_keys": list(mission.shared_memory.keys()),
        }

    @staticmethod
    def save_mission(mission: Mission, storage_dir: Path | str) -> Path:
        dir_path = Path(storage_dir) / "missions" / mission.project_name
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{mission.mission_id}.json"
        file_path.write_text(json.dumps(mission.to_dict(), indent=2), encoding="utf-8")
        return file_path

    @staticmethod
    def load_mission(storage_dir: Path | str, project_name: str, mission_id: str) -> Optional[Mission]:
        file_path = Path(storage_dir) / "missions" / project_name / f"{mission_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return Mission.from_dict(data)
