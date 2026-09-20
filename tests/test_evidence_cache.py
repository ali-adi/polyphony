"""Tests for EvidenceCache (Section 19: Evidence Cache)."""

import tempfile
import time
from pathlib import Path
import pytest

from orchestrator.evidence_cache import EvidenceCache, EvidenceEntry


def test_evidence_entry_fields():
    """Verify Section 19 required fields:
    source, timestamp, inputs, hash, result, valid_until.
    """
    entry = EvidenceEntry(
        source="pytest",
        timestamp=time.time(),
        inputs={"command": "pytest tests/test_cache.py"},
        hash="abc123hash",
        result={"passed": 19, "failed": 0},
        valid_until=time.time() + 60.0,
    )
    d = entry.to_dict()
    assert "source" in d
    assert "timestamp" in d
    assert "inputs" in d
    assert "hash" in d
    assert "result" in d
    assert "valid_until" in d

    recovered = EvidenceEntry.from_dict(d)
    assert recovered.source == "pytest"
    assert recovered.result == {"passed": 19, "failed": 0}


def test_evidence_cache_hit_and_miss():
    cache = EvidenceCache()
    inputs = {"test_path": "tests/test_foo.py", "flags": ["-v"]}

    # Miss
    assert cache.get("pytest", inputs) is None
    assert cache.misses == 1
    assert cache.hits == 0

    # Set
    cache.set("pytest", inputs, {"passed": 5, "failed": 0})

    # Hit
    cached_res = cache.get("pytest", inputs)
    assert cached_res == {"passed": 5, "failed": 0}
    assert cache.hits == 1
    assert cache.hit_rate == 0.5


def test_evidence_cache_ttl_expiration():
    cache = EvidenceCache()
    inputs = {"metric": "latency"}
    cache.set("benchmark", inputs, {"mean_ms": 12.5}, ttl_seconds=0.05)

    # Immediately available
    assert cache.get("benchmark", inputs) == {"mean_ms": 12.5}

    # Expired
    time.sleep(0.06)
    assert cache.get("benchmark", inputs) is None


def test_evidence_cache_dependency_invalidation():
    """Verify Section 19 requirement:
    'Invalidate it when its dependencies change.'
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        dep_file = tmp_path / "module.py"
        dep_file.write_text("def run(): return 42\n", encoding="utf-8")

        cache = EvidenceCache()
        inputs = {"command": "pytest tests/test_module.py"}
        res = {"passed": 10, "failed": 0}

        cache.set(
            "pytest",
            inputs,
            res,
            dependency_files=[dep_file],
        )

        # Before change: hit
        assert cache.get("pytest", inputs) == res

        # Modify dependency file
        dep_file.write_text("def run(): return 43 # modified\n", encoding="utf-8")

        # After change: invalidated!
        assert cache.get("pytest", inputs) is None


def test_evidence_cache_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "evidence_cache.json"
        cache1 = EvidenceCache(storage_path=storage_file)

        inputs = {"repo": "polyphony", "ref": "main"}
        cache1.set("git_status", inputs, {"clean": True})

        # Reload into separate instance
        cache2 = EvidenceCache(storage_path=storage_file)
        assert cache2.size() == 1
        res = cache2.get("git_status", inputs)
        assert res == {"clean": True}

        # Invalidate source
        deleted = cache2.invalidate("git_status")
        assert deleted == 1
        assert cache2.size() == 0
