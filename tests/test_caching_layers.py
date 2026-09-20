"""Tests for Caching Layers (Section 25: Caching Layers)."""

import tempfile
import time
from pathlib import Path
import pytest

from orchestrator.caching_layers import MultiLayerCache


def test_static_context_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        proj_dir = tmp_path / "my_project"
        proj_dir.mkdir()
        conv_file = proj_dir / "conventions.md"
        conv_file.write_text("# Conventions\n- Use black\n", encoding="utf-8")

        cache = MultiLayerCache()
        # 1. Fetch
        c1 = cache.get_static_context(proj_dir, "conventions.md")
        assert c1 == "# Conventions\n- Use black\n"

        # 2. Invalidation upon file edit
        time.sleep(0.01)
        conv_file.write_text("# Conventions\n- Use ruff\n", encoding="utf-8")
        c2 = cache.get_static_context(proj_dir, "conventions.md")
        assert c2 == "# Conventions\n- Use ruff\n"


def test_task_context_cache():
    cache = MultiLayerCache()
    task_id = "task-001"
    goal = "Implement caching"
    ac = ["ac1", "ac2"]
    files = ["src/cache.py"]

    # Miss
    assert cache.get_task_context(task_id, goal, ac, files) is None

    # Set
    cache.set_task_context(task_id, goal, ac, files, {"context_tokens": 1200, "plan": "Do X"})

    # Hit
    hit = cache.get_task_context(task_id, goal, ac, files)
    assert hit is not None
    assert hit["context_tokens"] == 1200

    # Invalidation on criteria change
    ac_changed = ["ac1", "ac2", "ac3_new"]
    assert cache.get_task_context(task_id, goal, ac_changed, files) is None


def test_semantic_cache():
    """Verify Section 25 semantic cache for equivalent / near-equivalent questions."""
    cache = MultiLayerCache()
    query = "How is database connection pooling configured in Postgres?"
    answer = "Use max_connections=20 with pgbouncer in transaction mode."

    cache.set_semantic(query, answer, ttl_seconds=60.0)

    # Near equivalent question
    near_query = "How is database connection pooling configured Postgres?"
    cached_ans = cache.get_semantic(near_query, similarity_threshold=0.80)
    assert cached_ans == answer

    # Unrelated question should miss
    unrelated_query = "What is the capital of France?"
    assert cache.get_semantic(unrelated_query) is None


def test_evidence_cache_integration():
    cache = MultiLayerCache()
    inputs = {"test_target": "tests/test_foo.py"}
    cache.set_evidence("pytest", inputs, {"passed": 12, "failed": 0})

    res = cache.get_evidence("pytest", inputs)
    assert res == {"passed": 12, "failed": 0}

    stats = cache.stats()
    assert stats["evidence_entries"] == 1
    assert stats["evidence_hits"] == 1
