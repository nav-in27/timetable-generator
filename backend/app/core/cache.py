"""
Lightweight in-memory TTL cache with tag-based invalidation.

Design goals:
- Zero external dependencies (no Redis/Memcached required for dev/SQLite mode)
- Thread-safe via threading.Lock
- Tag-based invalidation: when a teacher is updated, invalidate all "teacher" tagged entries
- Automatic stale-entry cleanup
- Hard size cap to prevent memory leaks

Usage:
    from app.core.cache import cache

    # Read-through pattern
    value = cache.get("teacher:5")
    if value is None:
        value = expensive_db_query()
        cache.set("teacher:5", value, ttl=60, tags=["teachers"])

    # Invalidate all teacher caches when data changes
    cache.invalidate_tag("teachers")

    # Invalidate everything (e.g., after import/generation)
    cache.clear()
"""

import threading
import time
from typing import Any, Dict, List, Optional, Set


class _CacheEntry:
    __slots__ = ("value", "expires_at", "tags")

    def __init__(self, value: Any, expires_at: float, tags: tuple):
        self.value = value
        self.expires_at = expires_at
        self.tags = tags


class TTLCache:
    """Thread-safe in-memory cache with TTL and tag-based invalidation."""

    def __init__(self, default_ttl: int = 120, max_size: int = 2048):
        self._store: Dict[str, _CacheEntry] = {}
        self._tag_keys: Dict[str, Set[str]] = {}  # tag -> set of keys
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache. Returns None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() > entry.expires_at:
                # Expired - clean up
                self._remove_entry(key, entry)
                self._misses += 1
                return None
            self._hits += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ):
        """Store a value in cache with optional TTL and tags for group invalidation."""
        if ttl is None:
            ttl = self._default_ttl
        tag_tuple = tuple(tags) if tags else ()

        with self._lock:
            # Evict if over capacity
            if len(self._store) >= self._max_size and key not in self._store:
                self._evict_expired_or_oldest()

            entry = _CacheEntry(
                value=value,
                expires_at=time.monotonic() + ttl,
                tags=tag_tuple,
            )

            # Remove old entry's tag references if replacing
            old = self._store.get(key)
            if old is not None:
                self._remove_tag_refs(key, old.tags)

            self._store[key] = entry

            # Register tags
            for tag in tag_tuple:
                if tag not in self._tag_keys:
                    self._tag_keys[tag] = set()
                self._tag_keys[tag].add(key)

    def invalidate(self, key: str):
        """Remove a specific key from cache."""
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                self._remove_entry(key, entry)

    def invalidate_tag(self, tag: str):
        """Remove ALL entries associated with a tag."""
        with self._lock:
            keys = self._tag_keys.pop(tag, set())
            for key in keys:
                entry = self._store.pop(key, None)
                if entry is not None:
                    # Remove from other tag sets too
                    for other_tag in entry.tags:
                        if other_tag != tag and other_tag in self._tag_keys:
                            self._tag_keys[other_tag].discard(key)

    def invalidate_tags(self, tags: List[str]):
        """Invalidate multiple tags at once."""
        for tag in tags:
            self.invalidate_tag(tag)

    def clear(self):
        """Remove all entries."""
        with self._lock:
            self._store.clear()
            self._tag_keys.clear()

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
                "tags": len(self._tag_keys),
            }

    # ---- Internal helpers (called with lock held) ----

    def _remove_entry(self, key: str, entry: _CacheEntry):
        self._store.pop(key, None)
        self._remove_tag_refs(key, entry.tags)

    def _remove_tag_refs(self, key: str, tags: tuple):
        for tag in tags:
            tag_set = self._tag_keys.get(tag)
            if tag_set is not None:
                tag_set.discard(key)
                if not tag_set:
                    del self._tag_keys[tag]

    def _evict_expired_or_oldest(self):
        """Remove expired entries first; if still over cap, remove oldest."""
        now = time.monotonic()
        expired_keys = [
            k for k, e in self._store.items() if now > e.expires_at
        ]
        for k in expired_keys:
            entry = self._store.get(k)
            if entry:
                self._remove_entry(k, entry)

        # If still over max, remove the 10% oldest entries
        if len(self._store) >= self._max_size:
            entries_sorted = sorted(
                self._store.items(), key=lambda kv: kv[1].expires_at
            )
            to_remove = max(1, self._max_size // 10)
            for k, entry in entries_sorted[:to_remove]:
                self._remove_entry(k, entry)


# ============================================================================
# Singleton cache instance
# ============================================================================
cache = TTLCache(default_ttl=120, max_size=2048)
