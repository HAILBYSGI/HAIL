# core/phase_summary_cache.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

from __future__ import annotations
import time
import threading
from typing import Callable, Dict, Optional

class PhaseSummaryCache:
    """
    Lightweight expiring cache for per-phase summaries.

    - set_summary(phase, summary): store/update entry with timestamp
    - get_summary(phase): return fresh summary or None if expired/missing
    - clear_cache(): drop all entries
    - invalidate(phase): remove a single phase entry
    - get_or_set(phase, builder): fetch from cache or compute+store via builder()
    - stats(): basic metrics for observability

    Thread-safe; optional max_size for simple LRU-style eviction.
    """

    def __init__(self, expiration_seconds: int = 3600, max_size: Optional[int] = 256):
        self._expiration = max(1, int(expiration_seconds))
        self._max_size = max_size if (max_size is None or max_size > 0) else 256
        self._cache: Dict[str, Dict[str, object]] = {}
        self._lock = threading.RLock()

    # -------- internal time helpers --------
    @staticmethod
    def _now() -> float:
        return time.time()

    def _expired(self, ts: float) -> bool:
        return (self._now() - ts) >= self._expiration

    # -------- public API --------
    def set_summary(self, phase_name: str, summary_text: str) -> None:
        """
        Store/refresh cached summary for a phase.
        Evicts oldest items if max_size is exceeded.
        """
        with self._lock:
            self._cache[phase_name] = {
                "summary": summary_text,
                "timestamp": self._now(),
                "last_access": self._now(),
            }
            self._evict_if_needed()

    def get_summary(self, phase_name: str) -> Optional[str]:
        """
        Returns cached summary if present and not expired; otherwise None.
        """
        with self._lock:
            entry = self._cache.get(phase_name)
            if not entry:
                return None
            if self._expired(float(entry["timestamp"])):  # type: ignore[arg-type]
                # expire
                del self._cache[phase_name]
                return None
            # touch for LRU
            entry["last_access"] = self._now()
            return str(entry["summary"])

    def get_or_set(self, phase_name: str, builder: Callable[[], str]) -> str:
        """
        Return a fresh cached summary or build it via `builder()`, store, and return.
        """
        val = self.get_summary(phase_name)
        if val is not None:
            return val
        # build outside lock to avoid long critical section
        built = builder()
        self.set_summary(phase_name, built)
        return built

    def invalidate(self, phase_name: str) -> bool:
        """
        Remove a single phase entry. Returns True if removed.
        """
        with self._lock:
            return self._cache.pop(phase_name, None) is not None

    def clear_cache(self) -> None:
        """
        Clears all cached summaries.
        """
        with self._lock:
            self._cache.clear()

    def stats(self) -> Dict[str, object]:
        """
        Basic metrics for observability and debugging.
        """
        with self._lock:
            size = len(self._cache)
            fresh = sum(0 if self._expired(float(e["timestamp"])) else 1 for e in self._cache.values())  # type: ignore[arg-type]
            return {
                "size": size,
                "fresh_entries": fresh,
                "expiry_seconds": self._expiration,
                "max_size": self._max_size,
            }

    # -------- eviction --------
    def _evict_if_needed(self) -> None:
        if self._max_size is None:
            return
        over = len(self._cache) - int(self._max_size)
        if over <= 0:
            return
        # Evict least-recently-accessed entries
        victims = sorted(self._cache.items(), key=lambda kv: float(kv[1].get("last_access", 0.0)))[:over]
        for k, _ in victims:
            self._cache.pop(k, None)


# Example usage
if __name__ == "__main__":
    cache = PhaseSummaryCache(expiration_seconds=2, max_size=2)
    cache.set_summary("Phase 1", "Founder verification & core protection.")
    print(cache.get_summary("Phase 1"))  # -> summary
    time.sleep(1)
    print(cache.get_summary("Phase 1"))  # -> still valid
    time.sleep(2)
    print(cache.get_summary("Phase 1"))  # -> None (expired)

    # LRU demo
    cache.set_summary("A", "a")
    cache.set_summary("B", "b")
    cache.get_summary("A")  # touch A to keep
    cache.set_summary("C", "c")  # should evict least recently used (B)
    print(cache.get_summary("B"))  # -> None if evicted
    print(cache.stats())
