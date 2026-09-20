"""Orchestration DAG engine supporting parallel execution, fan-out, fan-in, and branching (Section 32).

Section 32: Orchestration DAG
Support:
- task dependencies
- parallel execution
- fan-out
- fan-in
- retries
- conditional branches
- reviewer stages
- failure propagation
- cancellation
"""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("polyphony.dag")


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class DAGNode:
    """Individual execution unit in an orchestration DAG."""
    id: str
    name: str
    stage_type: str = "implementation"  # research, implementation, review, verification, etc.
    dependencies: List[str] = field(default_factory=list)
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    max_retries: int = 2
    retries_attempted: int = 0
    fn: Optional[Callable[[Dict[str, Any]], Any]] = None
    status: NodeStatus = NodeStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None

    def can_run(self, completed_node_ids: Set[str], context: Dict[str, Any]) -> bool:
        if self.status != NodeStatus.PENDING:
            return False
        # Check all dependencies are completed
        if not all(dep in completed_node_ids for dep in self.dependencies):
            return False
        # Check conditional branch
        if self.condition and not self.condition(context):
            self.status = NodeStatus.SKIPPED
            return False
        return True


class DAG:
    """Directed Acyclic Graph orchestrator for parallel and branching execution."""

    def __init__(self):
        self.nodes: Dict[str, DAGNode] = {}
        self._cancelled: bool = False

    def add_node(
        self,
        node_id: str,
        name: str,
        stage_type: str = "implementation",
        dependencies: Optional[List[str]] = None,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
        max_retries: int = 2,
        fn: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> DAGNode:
        node = DAGNode(
            id=node_id,
            name=name,
            stage_type=stage_type,
            dependencies=dependencies or [],
            condition=condition,
            max_retries=max_retries,
            fn=fn,
        )
        self.nodes[node_id] = node
        return node

    def add_dependency(self, child_id: str, parent_id: str) -> None:
        if child_id not in self.nodes:
            raise KeyError(f"Child node '{child_id}' not found in DAG")
        if parent_id not in self.nodes:
            raise KeyError(f"Parent node '{parent_id}' not found in DAG")
        if parent_id not in self.nodes[child_id].dependencies:
            self.nodes[child_id].dependencies.append(parent_id)

    def validate(self) -> bool:
        """Topological sort check to verify DAG is acyclic."""
        visited = set()
        recursion_stack = set()

        def _dfs(node_id: str) -> bool:
            visited.add(node_id)
            recursion_stack.add(node_id)
            for dep in self.nodes[node_id].dependencies:
                if dep not in visited:
                    if _dfs(dep):
                        return True
                elif dep in recursion_stack:
                    return True  # Cycle detected
            recursion_stack.remove(node_id)
            return False

        for n_id in self.nodes:
            if n_id not in visited:
                if _dfs(n_id):
                    raise ValueError(f"Cycle detected in DAG involving node '{n_id}'")
        return True

    def cancel(self) -> None:
        """Cancel all pending or running nodes."""
        self._cancelled = True
        for node in self.nodes.values():
            if node.status in (NodeStatus.PENDING, NodeStatus.RUNNING):
                node.status = NodeStatus.CANCELLED

    def execute(
        self,
        concurrency: int = 4,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the DAG honoring fan-out, fan-in, retries, and failure propagation."""
        self.validate()
        context: Dict[str, Any] = initial_context.copy() if initial_context else {}
        completed_ids: Set[str] = set()
        failed_ids: Set[str] = set()

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            while len(completed_ids) + len(failed_ids) < len(self.nodes):
                if self._cancelled:
                    break

                # 1. Failure propagation: cancel/fail downstream nodes if dependency failed
                for node in self.nodes.values():
                    if node.status == NodeStatus.PENDING:
                        failed_deps = [dep for dep in node.dependencies if dep in failed_ids]
                        if failed_deps:
                            node.status = NodeStatus.FAILED
                            node.error = f"Upstream dependency failed: {', '.join(failed_deps)}"
                            failed_ids.add(node.id)

                # 2. Find ready nodes for execution
                ready_nodes = [
                    node for node in self.nodes.values()
                    if node.can_run(completed_ids, context)
                ]

                # Check if some nodes were skipped
                for node in self.nodes.values():
                    if node.status == NodeStatus.SKIPPED and node.id not in completed_ids and node.id not in failed_ids:
                        completed_ids.add(node.id)

                if not ready_nodes and len(completed_ids) + len(failed_ids) < len(self.nodes):
                    # Check if any nodes are still running
                    running = [n for n in self.nodes.values() if n.status == NodeStatus.RUNNING]
                    if not running:
                        # Deadlock or unresolvable dependencies
                        break

                if not ready_nodes:
                    continue

                # 3. Parallel dispatch (fan-out)
                futures = {}
                for node in ready_nodes:
                    node.status = NodeStatus.RUNNING
                    if node.fn:
                        fut = pool.submit(self._run_node_with_retry, node, context)
                        futures[fut] = node
                    else:
                        node.status = NodeStatus.COMPLETED
                        completed_ids.add(node.id)

                # 4. Await current batch (fan-in join)
                for fut in concurrent.futures.as_completed(futures):
                    node = futures[fut]
                    success, res, err = fut.result()
                    if success:
                        node.status = NodeStatus.COMPLETED
                        node.result = res
                        completed_ids.add(node.id)
                        context[f"{node.id}_result"] = res
                    else:
                        node.status = NodeStatus.FAILED
                        node.error = err
                        failed_ids.add(node.id)

        return {
            "success": len(failed_ids) == 0 and not self._cancelled,
            "completed": list(completed_ids),
            "failed": list(failed_ids),
            "cancelled": self._cancelled,
            "context": context,
            "statuses": {nid: n.status.value for nid, n in self.nodes.items()},
        }

    def _run_node_with_retry(self, node: DAGNode, context: Dict[str, Any]) -> Tuple[bool, Any, Optional[str]]:
        while node.retries_attempted <= node.max_retries:
            try:
                res = node.fn(context)
                return True, res, None
            except Exception as e:
                node.retries_attempted += 1
                if node.retries_attempted > node.max_retries:
                    return False, None, str(e)
                logger.warning(f"Node '{node.id}' failed (attempt {node.retries_attempted}/{node.max_retries}): {e}. Retrying...")
        return False, None, "Max retries exceeded"
