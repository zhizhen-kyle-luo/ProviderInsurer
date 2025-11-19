import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from datetime import datetime
import threading


class WORMCache:
    """write-once-read-many cache for llm responses"""

    def __init__(self, cache_dir: str = ".worm_cache", enable_persistence: bool = True):
        self.cache_dir = Path(cache_dir)
        self.enable_persistence = enable_persistence
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'writes': 0
        }

        if self.enable_persistence:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_cache()

    def _generate_key(self, system_prompt: str, user_prompt: str, metadata: Optional[Dict] = None) -> str:
        """generate deterministic hash key from prompts"""
        combined = f"{system_prompt}|||{user_prompt}"
        if metadata:
            try:
                combined += f"|||{json.dumps(metadata, sort_keys=True)}"
            except (TypeError, ValueError):
                combined += f"|||{str(metadata)}"
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def _get_cache_path(self, key: str) -> Path:
        """get file path for cache entry"""
        return self.cache_dir / f"{key}.json"

    def _load_cache(self):
        """load all cache entries from disk"""
        if not self.cache_dir.exists():
            return

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    key = cache_file.stem
                    self.cache[key] = data
            except Exception as e:
                print(f"warning: failed to load cache file {cache_file}: {e}")

    def _write_to_disk(self, key: str, entry: Dict[str, Any]):
        """persist cache entry to disk"""
        if not self.enable_persistence:
            return

        cache_path = self._get_cache_path(key)
        try:
            with open(cache_path, 'w') as f:
                json.dump(entry, f, indent=2)
        except Exception as e:
            print(f"warning: failed to persist cache entry {key}: {e}")

    def get(self, system_prompt: str, user_prompt: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """retrieve cached response if exists"""
        key = self._generate_key(system_prompt, user_prompt, metadata)

        with self.lock:
            if key in self.cache:
                self.stats['hits'] += 1
                return self.cache[key]['response']

            self.stats['misses'] += 1
            return None

    def put(self, system_prompt: str, user_prompt: str, response: str, metadata: Optional[Dict] = None) -> bool:
        """write response to cache (write-once only)"""
        if response is None or response == "":
            return False

        key = self._generate_key(system_prompt, user_prompt, metadata)

        entry = {
            'system_prompt': system_prompt,
            'user_prompt': user_prompt,
            'response': response,
            'metadata': metadata or {},
            'timestamp': datetime.utcnow().isoformat(),
            'key': key
        }

        with self.lock:
            if key in self.cache:
                return False
            self.cache[key] = entry
            self.stats['writes'] += 1

        self._write_to_disk(key, entry)
        return True

    def get_or_compute(
        self,
        system_prompt: str,
        user_prompt: str,
        compute_fn: Callable[[], str],
        metadata: Optional[Dict] = None
    ) -> tuple[str, bool]:
        """get cached response or compute and cache it. returns (response, is_cache_hit)"""
        cached = self.get(system_prompt, user_prompt, metadata)
        if cached is not None:
            return cached, True

        response = compute_fn()
        if response is not None and response != "":
            self.put(system_prompt, user_prompt, response, metadata)
        return response, False

    def get_stats(self) -> Dict[str, Any]:
        """get cache statistics"""
        with self.lock:
            total = self.stats['hits'] + self.stats['misses']
            hit_rate = self.stats['hits'] / total if total > 0 else 0.0

            return {
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'writes': self.stats['writes'],
                'hit_rate': hit_rate,
                'cache_size': len(self.cache)
            }

    def clear(self):
        """clear all cache entries (use with caution)"""
        with self.lock:
            self.cache.clear()
            self.stats = {'hits': 0, 'misses': 0, 'writes': 0}

            if self.enable_persistence and self.cache_dir.exists():
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()

    def export_cache(self, output_path: str):
        """export entire cache to a single json file"""
        with self.lock:
            with open(output_path, 'w') as f:
                json.dump({
                    'cache': self.cache,
                    'stats': self.stats,
                    'exported_at': datetime.utcnow().isoformat()
                }, f, indent=2)
