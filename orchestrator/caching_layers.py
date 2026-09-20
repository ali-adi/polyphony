"""Multi-layer caching architecture for Polyphony (Section 25).

Section 25: Caching Layers
- Static context cache (global rules, project conventions, architecture)
- Task context cache (task objective, acceptance criteria, relevant files)
- Evidence cache (tests, benchmarks, git state, static analysis)
- Semantic cache (equivalent / near-equivalent questions)

All cache entries need invalidation rules.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from orchestrator.evidence_cache import EvidenceCache

logger = logging.getLogger("polyphony.caching_layers")


class CacheLayerType(str, Enum):
    STATIC_CONTEXT = "STATIC_CONTEXT"
    TASK_CONTEXT = "TASK_CONTEXT"
    EVIDENCE = "EVIDENCE"
    SEMANTIC = "SEMANTIC"


def _tokenize_text(text: str) -> Set[str]:
    return set(re.findall(r"\b\w{2,}\b", text.lower()))


def _jaccard_similarity(s1: Set[str], s2: Set[str]) -> float:
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / float(len(s1 | s2))


@dataclass
class SemanticCacheEntry:
    query: str
    tokens: Set[str]
    answer: Any
    timestamp: float
    ttl: Optional[float] = None

    def is_expired(self) -> bool:
        if self.ttl is not None and (time.time() - self.timestamp) > self.ttl:
            return True
        return False


class MultiLayerCache:
    """Unified manager for Static, Task, Evidence, and Semantic caches."""

    def __init__(self, storage_dir: Optional[Union[str, Path]] = None):
        self.storage_dir = Path(storage_dir).resolve() if storage_dir else None
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 1. Static context cache: key -> {hash, data}
        self._static_cache: Dict[str, Dict[str, Any]] = {}
        # 2. Task context cache: task_id -> {fingerprint, data}
        self._task_cache: Dict[str, Dict[str, Any]] = {}
        # 3. Evidence cache: backed by EvidenceCache
        evidence_storage = (self.storage_dir / "evidence.json") if self.storage_dir else None
        self.evidence_cache = EvidenceCache(storage_path=evidence_storage)
        # 4. Semantic cache: entries with text queries
        self._semantic_cache: List[SemanticCacheEntry] = []

    # ================= 1. STATIC CONTEXT CACHE =================
    def get_static_context(self, project_path: Union[str, Path], filename: str) -> Optional[str]:
        """Retrieve static context file content if unchanged since cached."""
        p = Path(project_path).resolve() / filename
        if not p.is_file():
            return None

        # Check mtime and file hash for invalidation
        try:
            mtime = p.stat().st_mtime
            cached = self._static_cache.get(str(p))
            if cached and cached.get("mtime") == mtime:
                return cached["content"]

            content = p.read_text(encoding="utf-8")
            self._static_cache[str(p)] = {"mtime": mtime, "content": content}
            return content
        except OSError:
            return None

    def invalidate_static_context(self, file_path: Optional[Union[str, Path]] = None) -> None:
        if file_path:
            self._static_cache.pop(str(Path(file_path).resolve()), None)
        else:
            self._static_cache.clear()

    # ================= 2. TASK CONTEXT CACHE =================
    def get_task_context(
        self,
        task_id: str,
        goal: str,
        acceptance_criteria: List[str],
        relevant_files: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached task context if objective, criteria, and files are unchanged."""
        fingerprint = hashlib.sha256(
            json.dumps({"goal": goal, "ac": sorted(acceptance_criteria), "files": sorted(relevant_files)}).encode()
        ).hexdigest()

        cached = self._task_cache.get(task_id)
        if cached and cached.get("fingerprint") == fingerprint:
            return cached.get("data")
        return None

    def set_task_context(
        self,
        task_id: str,
        goal: str,
        acceptance_criteria: List[str],
        relevant_files: List[str],
        data: Dict[str, Any],
    ) -> None:
        fingerprint = hashlib.sha256(
            json.dumps({"goal": goal, "ac": sorted(acceptance_criteria), "files": sorted(relevant_files)}).encode()
        ).hexdigest()
        self._task_cache[task_id] = {"fingerprint": fingerprint, "data": data}

    def invalidate_task_context(self, task_id: Optional[str] = None) -> None:
        if task_id:
            self._task_cache.pop(task_id, None)
        else:
            self._task_cache.clear()

    # ================= 3. EVIDENCE CACHE =================
    def get_evidence(
        self,
        source: str,
        inputs: Dict[str, Any],
        dependency_files: Optional[List[Union[str, Path]]] = None,
    ) -> Optional[Any]:
        return self.evidence_cache.get(source, inputs, dependency_files=dependency_files)

    def set_evidence(
        self,
        source: str,
        inputs: Dict[str, Any],
        result: Any,
        ttl_seconds: Optional[float] = None,
        dependency_files: Optional[List[Union[str, Path]]] = None,
    ) -> None:
        self.evidence_cache.set(source, inputs, result, ttl_seconds=ttl_seconds, dependency_files=dependency_files)

    # ================= 4. SEMANTIC CACHE =================
    def get_semantic(self, query: str, similarity_threshold: float = 0.80) -> Optional[Any]:
        """Find answer to equivalent or near-equivalent questions via semantic token overlap."""
        tokens = _tokenize_text(query)
        if not tokens:
            return None

        # Clean expired entries
        self._semantic_cache = [e for e in self._semantic_cache if not e.is_expired()]

        best_score = 0.0
        best_entry = None
        for entry in self._semantic_cache:
            score = _jaccard_similarity(tokens, entry.tokens)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score >= similarity_threshold:
            logger.debug(f"Semantic cache hit with score {best_score:.2f} for query: '{query}'")
            return best_entry.answer
        return None

    def set_semantic(self, query: str, answer: Any, ttl_seconds: Optional[float] = 3600.0) -> None:
        tokens = _tokenize_text(query)
        self._semantic_cache.append(
            SemanticCacheEntry(
                query=query,
                tokens=tokens,
                answer=answer,
                timestamp=time.time(),
                ttl=ttl_seconds,
            )
        )

    def invalidate_semantic(self) -> None:
        self._semantic_cache.clear()

    # ================= GENERAL =================
    def invalidate_all(self) -> None:
        self.invalidate_static_context()
        self.invalidate_task_context()
        self.evidence_cache.invalidate()
        self.invalidate_semantic()

    def stats(self) -> Dict[str, Any]:
        return {
            "static_entries": len(self._static_cache),
            "task_entries": len(self._task_cache),
            "evidence_entries": self.evidence_cache.size(),
            "evidence_hits": self.evidence_cache.hits,
            "evidence_misses": self.evidence_cache.misses,
            "semantic_entries": len(self._semantic_cache),
        }
