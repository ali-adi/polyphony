"""Tests for Knowledge and Memory System with Quality Controls (Sections 30 & 31)."""

import tempfile
import time
from pathlib import Path
import pytest

from orchestrator.memory import (
    MemoryEntry,
    MemoryManager,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)


def test_memory_entry_fields():
    """Verify Section 30 YAML required fields:
    type, scope, source, created, updated, confidence, status, content.
    """
    mem = MemoryEntry(
        type=MemoryType.FAILURE,
        scope=MemoryScope.PROJECT,
        source="verifier",
        confidence=0.95,
        status=MemoryStatus.ACTIVE,
        content="This approach failed because regex parser could not handle nested brackets.",
        provenance={"task_id": "task-42", "file": "parser.py"},
    )
    d = mem.to_dict()
    assert d["type"] == "FAILURE"
    assert d["scope"] == "project"
    assert d["source"] == "verifier"
    assert "created" in d
    assert "updated" in d
    assert d["confidence"] == 0.95
    assert d["status"] == "active"
    assert "This approach failed" in d["content"]
    assert d["provenance"]["task_id"] == "task-42"


def test_failure_memory_prioritization():
    """Verify Section 30:
    Prioritize failure memory before fancy semantic/vector memory.
    """
    mgr = MemoryManager()
    mgr.add_memory("General code convention: 4 spaces", MemoryType.CONVENTION, confidence=0.8)
    mgr.add_memory("This approach failed because SQLite lock timed out under 10 threads", MemoryType.FAILURE, confidence=0.9)
    mgr.add_memory("Lesson learned: use WAL mode for concurrency", MemoryType.LESSON, confidence=0.85)

    # get_failure_memories
    failures = mgr.get_failure_memories(["sqlite", "concurrency"])
    assert len(failures) == 1
    assert "SQLite lock timed out" in failures[0].content

    # query sorts failure memories first
    all_active = mgr.query()
    assert all_active[0].type == MemoryType.FAILURE


def test_quality_controls_confidence_filtering():
    """Verify Section 31:
    Do not allow low-confidence agent speculation to silently become permanent project truth.
    """
    mgr = MemoryManager()
    # Speculation with low confidence (0.3)
    entry, err = mgr.add_memory(
        "Maybe we should rewrite the whole backend in Rust",
        MemoryType.ARCHITECTURE,
        confidence=0.3,
    )
    assert entry is None
    assert "below acceptable threshold" in err
    assert len(mgr.query()) == 0


def test_quality_controls_human_approval_for_architecture():
    """Verify Section 31:
    Human approval for important architectural decisions.
    """
    mgr = MemoryManager()
    entry, err = mgr.add_memory(
        "Adopt event-driven architecture using Kafka message bus",
        MemoryType.ARCHITECTURE,
        confidence=0.95,
        human_approved=False,
    )
    assert entry is not None
    assert entry.status == MemoryStatus.PENDING_APPROVAL

    # Active query does not include pending approval
    active = mgr.query(active_only=True)
    assert len(active) == 0

    # Human approves
    assert mgr.approve_memory(entry.id) is True
    assert entry.status == MemoryStatus.ACTIVE
    assert len(mgr.query(active_only=True)) == 1


def test_quality_controls_deduplication_and_contradiction():
    """Verify Section 31:
    Deduplication and contradiction detection / supersession.
    """
    mgr = MemoryManager()

    # 1. Deduplication
    e1, _ = mgr.add_memory("Always format with ruff check", MemoryType.RULE, confidence=0.8)
    e2, msg = mgr.add_memory("always format with ruff check", MemoryType.RULE, confidence=0.9)
    assert e1.id == e2.id
    assert "Updated existing" in msg
    assert e1.confidence == 0.9

    # 2. Contradiction & supersession
    e_contra, _ = mgr.add_memory("Never format with ruff check", MemoryType.RULE, confidence=0.95)
    # Since e_contra had higher confidence (0.95 > 0.9), e1 is superseded!
    assert e1.status == MemoryStatus.SUPERSEDED
    assert e1.superseded_by == e_contra.id


def test_quality_controls_ttl_and_promotion():
    """Verify Section 31:
    Expiration/TTL and automatic/manual promotion from project to global.
    """
    mgr = MemoryManager()
    entry, _ = mgr.add_memory(
        "Temporary workaround for flaky CI network",
        MemoryType.KNOWN_ISSUE,
        confidence=0.9,
        ttl_seconds=0.05,
    )
    assert len(mgr.query()) == 1
    time.sleep(0.06)
    # Expired entry evicted on query
    assert len(mgr.query()) == 0

    # Promotion to global
    perm_entry, _ = mgr.add_memory(
        "Python 3.14 deprecation policy",
        MemoryType.CONVENTION,
        scope=MemoryScope.PROJECT,
        confidence=0.95,
    )
    assert perm_entry.scope == MemoryScope.PROJECT
    promoted = mgr.promote_to_global(perm_entry.id)
    assert promoted is True
    assert perm_entry.scope == MemoryScope.GLOBAL
