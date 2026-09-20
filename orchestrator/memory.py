"""Formalized knowledge, memory system, and quality controls (Sections 30 & 31).

Section 30: Knowledge and Memory
Formal memory types:
RULE, DECISION, CONVENTION, FAILURE, LESSON, ARCHITECTURE, KNOWN_ISSUE, SKILL, EXPERIMENT.
Each memory contains:
- type:
- scope:
- source:
- created:
- updated:
- confidence:
- status:
- content:

Prioritize failure memory ("This approach failed because X").

Section 31: Memory Quality Controls
- deduplication
- contradiction detection
- provenance
- confidence
- expiration/TTL
- supersession
- project/global scoping
- automatic promotion
- human approval for important architectural decisions
Do not allow low-confidence agent speculation to silently become permanent project truth.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("polyphony.memory")


class MemoryType(str, Enum):
    RULE = "RULE"
    DECISION = "DECISION"
    CONVENTION = "CONVENTION"
    FAILURE = "FAILURE"
    LESSON = "LESSON"
    ARCHITECTURE = "ARCHITECTURE"
    KNOWN_ISSUE = "KNOWN_ISSUE"
    SKILL = "SKILL"
    EXPERIMENT = "EXPERIMENT"


class MemoryScope(str, Enum):
    PROJECT = "project"
    GLOBAL = "global"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    PENDING_APPROVAL = "pending_approval"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclass
class MemoryEntry:
    """Individual memory item complying with Section 30."""
    id: str = field(default_factory=lambda: f"mem-{uuid.uuid4().hex[:8]}")
    type: MemoryType = MemoryType.LESSON
    scope: MemoryScope = MemoryScope.PROJECT
    source: str = "orchestrator"
    created: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    confidence: float = 1.0
    status: MemoryStatus = MemoryStatus.ACTIVE
    content: str = ""

    # Quality control metadata (Section 31)
    provenance: Dict[str, Any] = field(default_factory=dict)
    superseded_by: Optional[str] = None
    ttl_seconds: Optional[float] = None
    created_epoch: float = field(default_factory=time.time)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        if self.ttl_seconds is None:
            return False
        now = current_time if current_time is not None else time.time()
        return (now - self.created_epoch) > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "scope": self.scope.value,
            "source": self.source,
            "created": self.created,
            "updated": self.updated,
            "confidence": self.confidence,
            "status": self.status.value,
            "content": self.content,
            "provenance": self.provenance,
            "superseded_by": self.superseded_by,
            "ttl_seconds": self.ttl_seconds,
            "created_epoch": self.created_epoch,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MemoryEntry:
        return cls(
            id=data.get("id", f"mem-{uuid.uuid4().hex[:8]}"),
            type=MemoryType(data.get("type", MemoryType.LESSON.value)),
            scope=MemoryScope(data.get("scope", MemoryScope.PROJECT.value)),
            source=data.get("source", "orchestrator"),
            created=data.get("created", datetime.datetime.now().isoformat()),
            updated=data.get("updated", datetime.datetime.now().isoformat()),
            confidence=float(data.get("confidence", 1.0)),
            status=MemoryStatus(data.get("status", MemoryStatus.ACTIVE.value)),
            content=data.get("content", ""),
            provenance=data.get("provenance", {}),
            superseded_by=data.get("superseded_by"),
            ttl_seconds=data.get("ttl_seconds"),
            created_epoch=data.get("created_epoch", time.time()),
        )


class MemoryManager:
    """Manages storage, retrieval, and quality controls for memory items."""

    # Low-confidence threshold: speculations below this are blocked from becoming truth
    MIN_ACCEPTABLE_CONFIDENCE = 0.50

    def __init__(self, storage_path: Optional[Union[str, Path]] = None):
        self.storage_path = Path(storage_path).resolve() if storage_path else None
        self._memories: Dict[str, MemoryEntry] = {}
        if self.storage_path and self.storage_path.exists():
            self._load()

    def add_memory(
        self,
        content: str,
        memory_type: Union[MemoryType, str],
        scope: Union[MemoryScope, str] = MemoryScope.PROJECT,
        source: str = "orchestrator",
        confidence: float = 1.0,
        provenance: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
        human_approved: bool = False,
    ) -> Tuple[Optional[MemoryEntry], Optional[str]]:
        """Add a new memory with quality controls (dedup, contradiction, confidence, approval)."""
        m_type = MemoryType(memory_type.value if isinstance(memory_type, MemoryType) else str(memory_type).upper())
        m_scope = MemoryScope(scope.value if isinstance(scope, MemoryScope) else str(scope).lower())

        # Quality Control 1: Confidence Filter
        if confidence < self.MIN_ACCEPTABLE_CONFIDENCE:
            logger.warning(f"Rejected low-confidence speculation ({confidence:.2f}): '{content}'")
            return None, f"Confidence {confidence:.2f} below acceptable threshold {self.MIN_ACCEPTABLE_CONFIDENCE}"

        # Quality Control 2: Architectural human approval requirement
        status = MemoryStatus.ACTIVE
        if m_type == MemoryType.ARCHITECTURE and not human_approved:
            status = MemoryStatus.PENDING_APPROVAL
            logger.info("Architectural decision queued for human approval.")

        # Quality Control 3: Deduplication
        normalized_content = self._normalize_content(content)
        for existing in self._memories.values():
            if existing.status == MemoryStatus.ACTIVE and existing.type == m_type and existing.scope == m_scope:
                if self._normalize_content(existing.content) == normalized_content:
                    # Update existing instead of creating duplicate
                    existing.updated = datetime.datetime.now().isoformat()
                    existing.confidence = max(existing.confidence, confidence)
                    if provenance:
                        existing.provenance.update(provenance)
                    self._save()
                    return existing, "Updated existing duplicate memory"

        # Quality Control 4: Contradiction Detection & Supersession
        contradiction = self._detect_contradiction(content, m_type, m_scope)
        if contradiction:
            # If new entry has higher confidence, supersede older contradiction
            if confidence >= contradiction.confidence:
                contradiction.status = MemoryStatus.SUPERSEDED
                logger.info(f"Memory {contradiction.id} superseded due to contradiction with higher confidence entry.")
            else:
                logger.warning(f"Contradiction detected with higher confidence memory {contradiction.id}. Marking new as superseded.")
                status = MemoryStatus.SUPERSEDED

        entry = MemoryEntry(
            type=m_type,
            scope=m_scope,
            source=source,
            confidence=confidence,
            status=status,
            content=content.strip(),
            provenance=provenance or {},
            ttl_seconds=ttl_seconds,
        )

        if contradiction and confidence >= contradiction.confidence:
            contradiction.superseded_by = entry.id

        self._memories[entry.id] = entry
        self._save()
        return entry, None

    def approve_memory(self, memory_id: str) -> bool:
        """Human approval for pending architectural decisions."""
        entry = self._memories.get(memory_id)
        if entry and entry.status == MemoryStatus.PENDING_APPROVAL:
            entry.status = MemoryStatus.ACTIVE
            entry.updated = datetime.datetime.now().isoformat()
            self._save()
            return True
        return False

    def promote_to_global(self, memory_id: str, min_confidence: float = 0.85) -> bool:
        """Promote a project-scoped memory to global scope if confidence qualifies."""
        entry = self._memories.get(memory_id)
        if not entry or entry.status != MemoryStatus.ACTIVE:
            return False
        if entry.confidence < min_confidence:
            return False

        entry.scope = MemoryScope.GLOBAL
        entry.updated = datetime.datetime.now().isoformat()
        self._save()
        return True

    def supersede(self, old_memory_id: str, new_memory_id: str) -> bool:
        old_entry = self._memories.get(old_memory_id)
        new_entry = self._memories.get(new_memory_id)
        if old_entry and new_entry:
            old_entry.status = MemoryStatus.SUPERSEDED
            old_entry.superseded_by = new_memory_id
            old_entry.updated = datetime.datetime.now().isoformat()
            self._save()
            return True
        return False

    def get_failure_memories(self, keywords: Optional[List[str]] = None) -> List[MemoryEntry]:
        """Section 30: Prioritize failure memory ('This approach failed because X')."""
        failures = [
            m for m in self._memories.values()
            if m.type == MemoryType.FAILURE and m.status == MemoryStatus.ACTIVE and not m.is_expired()
        ]
        if not keywords:
            return failures

        # Filter by keyword relevance
        kws = {k.lower() for k in keywords}
        scored = []
        for f in failures:
            score = sum(1 for kw in kws if kw in f.content.lower())
            if score > 0:
                scored.append((score, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored]

    def query(
        self,
        memory_types: Optional[List[Union[MemoryType, str]]] = None,
        scope: Optional[Union[MemoryScope, str]] = None,
        active_only: bool = True,
        keywords: Optional[List[str]] = None,
    ) -> List[MemoryEntry]:
        """Query active, unexpired memories matching filters."""
        # Evict expired
        results = []
        target_types = {
            t.value if isinstance(t, MemoryType) else str(t).upper()
            for t in memory_types
        } if memory_types else None

        target_scope = scope.value if isinstance(scope, MemoryScope) else (str(scope).lower() if scope else None)

        for m in self._memories.values():
            if m.is_expired():
                m.status = MemoryStatus.EXPIRED
                continue

            if active_only and m.status != MemoryStatus.ACTIVE:
                continue

            if target_types and m.type.value not in target_types:
                continue

            if target_scope and m.scope.value != target_scope:
                continue

            if keywords:
                content_lower = m.content.lower()
                if not any(k.lower() in content_lower for k in keywords):
                    continue

            results.append(m)

        # Sort: Failure memories first, then highest confidence
        results.sort(key=lambda m: (m.type == MemoryType.FAILURE, m.confidence), reverse=True)
        return results

    def _normalize_content(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    def _detect_contradiction(
        self,
        content: str,
        m_type: MemoryType,
        m_scope: MemoryScope,
    ) -> Optional[MemoryEntry]:
        """Detect direct contradictions (e.g. 'always use X' vs 'never use X')."""
        norm = self._normalize_content(content)
        negation_pairs = [
            ("always ", "never "),
            ("must use ", "do not use "),
            ("enable ", "disable "),
            ("true", "false"),
        ]

        for entry in self._memories.values():
            if entry.status != MemoryStatus.ACTIVE or entry.type != m_type or entry.scope != m_scope:
                continue
            e_norm = self._normalize_content(entry.content)
            for pos, neg in negation_pairs:
                if (pos in norm and neg in e_norm) or (neg in norm and pos in e_norm):
                    # Check subject match
                    sub_pos = norm.replace(pos, "").replace(neg, "").strip()
                    sub_e = e_norm.replace(pos, "").replace(neg, "").strip()
                    if sub_pos and sub_e and (sub_pos in sub_e or sub_e in sub_pos):
                        return entry
        return None

    def _save(self) -> None:
        if not self.storage_path:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.to_dict() for k, v in self._memories.items()}
            self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save memories: {e}")

    def _load(self) -> None:
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._memories = {k: MemoryEntry.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning(f"Failed to load memories: {e}")
            self._memories = {}
