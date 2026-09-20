"""Evidence Cache for Polyphony.

Section 19: Evidence Cache
Cache objective evidence:
- test results
- benchmark results
- git status
- git diff
- file hashes
- dependency graph
- repository metadata
- static analysis

If nothing relevant changed, do not re-run expensive reasoning just to rediscover the same fact.

Every cached result has:
- source:
- timestamp:
- inputs:
- hash:
- result:
- valid_until:

Invalidate when dependencies change.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("polyphony.evidence_cache")


@dataclass
class EvidenceEntry:
    """Individual cached evidence item complying with Section 19."""
    source: str
    timestamp: float
    inputs: Dict[str, Any]
    hash: str
    result: Any
    valid_until: Optional[float] = None
    dependency_hashes: Dict[str, str] = field(default_factory=dict)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        if self.valid_until is not None and now > self.valid_until:
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "timestamp": self.timestamp,
            "inputs": self.inputs,
            "hash": self.hash,
            "result": self.result,
            "valid_until": self.valid_until,
            "dependency_hashes": self.dependency_hashes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceEntry:
        return cls(
            source=data.get("source", ""),
            timestamp=data.get("timestamp", 0.0),
            inputs=data.get("inputs", {}),
            hash=data.get("hash", ""),
            result=data.get("result"),
            valid_until=data.get("valid_until"),
            dependency_hashes=data.get("dependency_hashes", {}),
        )


class EvidenceCache:
    """Manages cached objective evidence and dependency-based invalidation."""

    def __init__(self, storage_path: Optional[Union[str, Path]] = None):
        self.storage_path = Path(storage_path).resolve() if storage_path else None
        self._entries: Dict[str, EvidenceEntry] = {}
        self._hits: int = 0
        self._misses: int = 0
        if self.storage_path and self.storage_path.exists():
            self._load()

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def compute_input_hash(self, source: str, inputs: Dict[str, Any]) -> str:
        """Deterministically compute SHA-256 hash of inputs."""
        serialized = json.dumps({"source": source, "inputs": inputs}, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _compute_file_hash(self, path: Union[str, Path]) -> Optional[str]:
        p = Path(path)
        if not p.is_file():
            return None
        h = hashlib.sha256()
        try:
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except OSError:
            return None

    def get(
        self,
        source: str,
        inputs: Dict[str, Any],
        dependency_files: Optional[List[Union[str, Path]]] = None,
    ) -> Optional[Any]:
        """Retrieve cached result if valid and dependencies are unchanged."""
        key = self.compute_input_hash(source, inputs)
        entry = self._entries.get(key)
        if not entry:
            self._misses += 1
            return None

        # 1. TTL Check
        if entry.is_expired():
            logger.debug(f"Cache expired for {source} (hash: {entry.hash})")
            del self._entries[key]
            self._misses += 1
            return None

        # 2. Dependency Invalidation Check
        dep_files = dependency_files or list(entry.dependency_hashes.keys())
        for fpath in dep_files:
            str_path = str(Path(fpath).resolve())
            recorded_hash = entry.dependency_hashes.get(str_path)
            current_hash = self._compute_file_hash(str_path)

            if recorded_hash is not None and current_hash != recorded_hash:
                logger.debug(f"Cache invalidated for {source}: dependency {str_path} changed")
                del self._entries[key]
                self._misses += 1
                return None

        self._hits += 1
        logger.debug(f"Cache HIT for {source} (hash: {entry.hash})")
        return entry.result

    def set(
        self,
        source: str,
        inputs: Dict[str, Any],
        result: Any,
        ttl_seconds: Optional[float] = None,
        dependency_files: Optional[List[Union[str, Path]]] = None,
    ) -> EvidenceEntry:
        """Store result in cache with recorded dependency hashes."""
        key = self.compute_input_hash(source, inputs)
        now = time.time()
        valid_until = now + ttl_seconds if ttl_seconds is not None else None

        dep_hashes = {}
        if dependency_files:
            for fpath in dependency_files:
                resolved_p = Path(fpath).resolve()
                f_hash = self._compute_file_hash(resolved_p)
                if f_hash is not None:
                    dep_hashes[str(resolved_p)] = f_hash

        entry = EvidenceEntry(
            source=source,
            timestamp=now,
            inputs=inputs,
            hash=key,
            result=result,
            valid_until=valid_until,
            dependency_hashes=dep_hashes,
        )
        self._entries[key] = entry
        self._save()
        return entry

    def invalidate(self, source: Optional[str] = None) -> int:
        """Invalidate entries by source or clear all."""
        if source is None:
            count = len(self._entries)
            self._entries.clear()
            self._save()
            return count

        to_del = [k for k, v in self._entries.items() if v.source == source]
        for k in to_del:
            del self._entries[k]
        self._save()
        return len(to_del)

    def size(self) -> int:
        return len(self._entries)

    def get_all_entries(self) -> List[EvidenceEntry]:
        return list(self._entries.values())

    def _save(self):
        if not self.storage_path:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.to_dict() for k, v in self._entries.items()}
            tmp_path = self.storage_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_path.replace(self.storage_path)
        except Exception as e:
            logger.warning(f"Failed to persist evidence cache: {e}")

    def _load(self):
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._entries = {k: EvidenceEntry.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning(f"Failed to load evidence cache: {e}")
            self._entries = {}
