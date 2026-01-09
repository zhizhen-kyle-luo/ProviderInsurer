#!/usr/bin/env python3
"""simple test for worm cache core functionality"""

import sys
import os
import shutil
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from src.utils.worm_cache import WORMCache


def test_worm_cache_basic():
    """test basic worm cache functionality"""
    print("testing basic worm cache...")

    cache = WORMCache(cache_dir=".test_cache", enable_persistence=False)

    # test write-once behavior
    system_prompt = "you are a helpful assistant"
    user_prompt = "what is 2+2?"
    response = "the answer is 4"

    # first write should succeed
    success = cache.put(system_prompt, user_prompt, response)
    assert success, "first write should succeed"

    # second write with same prompts should fail (write-once)
    success = cache.put(system_prompt, user_prompt, "different response")
    assert not success, "second write should fail (write-once property)"

    # read should return first response
    cached = cache.get(system_prompt, user_prompt)
    assert cached == response, f"expected '{response}', got '{cached}'"

    # stats should show correct values
    stats = cache.get_stats()
    assert stats['cache_size'] == 1, f"expected cache_size=1, got {stats['cache_size']}"
    assert stats['writes'] == 1, f"expected writes=1, got {stats['writes']}"

    print("  basic tests passed")


def test_worm_cache_get_or_compute():
    """test get_or_compute functionality"""
    print("testing get_or_compute...")

    cache = WORMCache(cache_dir=".test_cache", enable_persistence=False)

    call_count = 0

    def compute_fn():
        nonlocal call_count
        call_count += 1
        return f"computed result {call_count}"

    # first call should compute
    result1, is_hit1 = cache.get_or_compute("system", "user1", compute_fn)
    assert not is_hit1, "first call should be cache miss"
    assert call_count == 1, "compute function should be called once"
    assert result1 == "computed result 1"

    # second call with same prompts should use cache
    result2, is_hit2 = cache.get_or_compute("system", "user1", compute_fn)
    assert is_hit2, "second call should be cache hit"
    assert call_count == 1, "compute function should not be called again"
    assert result2 == "computed result 1", "should return cached result"

    # call with different prompts should compute
    result3, is_hit3 = cache.get_or_compute("system", "user2", compute_fn)
    assert not is_hit3, "call with different prompts should be cache miss"
    assert call_count == 2, "compute function should be called for new prompts"
    assert result3 == "computed result 2"

    print("  get_or_compute tests passed")


def test_cache_persistence():
    """test cache persistence to disk"""
    print("testing cache persistence...")

    test_dir = ".test_cache_persist"

    # clean up any existing test cache
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    # create cache with persistence
    cache1 = WORMCache(cache_dir=test_dir, enable_persistence=True)
    cache1.put("system1", "user1", "response1")
    cache1.put("system2", "user2", "response2")

    # create new cache instance (simulating restart)
    cache2 = WORMCache(cache_dir=test_dir, enable_persistence=True)

    # should load cached entries from disk
    result1 = cache2.get("system1", "user1")
    result2 = cache2.get("system2", "user2")

    assert result1 == "response1", "should load first entry from disk"
    assert result2 == "response2", "should load second entry from disk"

    stats = cache2.get_stats()
    print(f"  loaded {stats['cache_size']} entries from disk")

    # clean up
    shutil.rmtree(test_dir)

    print("  persistence tests passed")


def test_cache_key_generation():
    """test that cache keys are deterministic and unique"""
    print("testing cache key generation...")

    cache = WORMCache(cache_dir=".test_cache", enable_persistence=False)

    # same prompts should generate same key
    key1 = cache._generate_key("sys1", "user1")
    key2 = cache._generate_key("sys1", "user1")
    assert key1 == key2, "same prompts should generate same key"

    # different prompts should generate different keys
    key3 = cache._generate_key("sys1", "user2")
    assert key1 != key3, "different prompts should generate different keys"

    # metadata should affect key
    key4 = cache._generate_key("sys1", "user1", {"param": "value"})
    assert key1 != key4, "metadata should affect key generation"

    # non-serializable metadata should not crash
    class NonSerializable:
        pass

    key5 = cache._generate_key("sys1", "user1", {"obj": NonSerializable()})
    assert key5 is not None, "should handle non-serializable metadata"

    print("  key generation tests passed")


def test_edge_cases():
    """test edge cases and error conditions"""
    print("testing edge cases...")

    cache = WORMCache(cache_dir=".test_cache", enable_persistence=False)

    # should not cache None responses
    success = cache.put("sys", "user", None)
    assert not success, "should not cache None responses"

    # should not cache empty responses
    success = cache.put("sys", "user", "")
    assert not success, "should not cache empty responses"

    # empty prompts should work
    success = cache.put("", "", "response")
    assert success, "should handle empty prompts"
    assert cache.get("", "") == "response"

    # very long prompts should work
    long_prompt = "a" * 100000
    success = cache.put(long_prompt, "user", "response")
    assert success, "should handle very long prompts"
    assert cache.get(long_prompt, "user") == "response"

    # unicode characters should work
    success = cache.put("系统", "用户", "响应")
    assert success, "should handle unicode"
    assert cache.get("系统", "用户") == "响应"

    print("  edge case tests passed")


def test_thread_safety():
    """test that cache is thread-safe"""
    print("testing thread safety...")

    cache = WORMCache(cache_dir=".test_cache", enable_persistence=False)
    errors = []

    def write_worker(thread_id):
        try:
            for i in range(10):
                cache.put(f"sys_{thread_id}", f"user_{i}", f"response_{thread_id}_{i}")
        except Exception as e:
            errors.append(e)

    def read_worker(thread_id):
        try:
            for i in range(10):
                cache.get(f"sys_{thread_id}", f"user_{i}")
        except Exception as e:
            errors.append(e)

    # create multiple threads writing and reading concurrently
    threads = []
    for i in range(5):
        threads.append(threading.Thread(target=write_worker, args=(i,)))
        threads.append(threading.Thread(target=read_worker, args=(i,)))

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert len(errors) == 0, f"thread safety errors: {errors}"
    print("  thread safety tests passed")


if __name__ == "__main__":
    print("running worm cache tests...\n")

    test_worm_cache_basic()
    test_worm_cache_get_or_compute()
    test_cache_persistence()
    test_cache_key_generation()
    test_edge_cases()
    test_thread_safety()

    print("\nall core tests passed!")
    print("\nworm cache is ready to use")
