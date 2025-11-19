#!/usr/bin/env python3
"""test script for worm cache implementation"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.utils.worm_cache import WORMCache
from src.utils.cached_llm import CachedLLM


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

    # stats should show 1 hit, 0 misses (since we called get once after put)
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

    import shutil
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

    # clean up
    shutil.rmtree(test_dir)

    print("  persistence tests passed")


def test_cached_llm_wrapper():
    """test cached llm wrapper"""
    print("testing cached llm wrapper...")

    # create mock llm
    class MockLLM:
        def __init__(self):
            self.call_count = 0
            self.model_name = "mock-model"

        def invoke(self, messages, **kwargs):
            self.call_count += 1

            class MockResponse:
                def __init__(self, content):
                    self.content = content

            return MockResponse(f"mock response {self.call_count}")

    from langchain_core.messages import HumanMessage

    mock_llm = MockLLM()
    cache = WORMCache(cache_dir=".test_cache", enable_persistence=False)
    cached_llm = CachedLLM(mock_llm, cache, agent_name="test_agent")

    # first call should invoke underlying llm
    messages = [HumanMessage(content="test prompt")]
    response1 = cached_llm.invoke(messages)
    assert mock_llm.call_count == 1, "underlying llm should be called"
    assert response1.content == "mock response 1"
    assert not response1.additional_kwargs.get('cache_hit'), "first call should be cache miss"

    # second call with same messages should use cache
    response2 = cached_llm.invoke(messages)
    assert mock_llm.call_count == 1, "underlying llm should not be called again"
    assert response2.content == "mock response 1", "should return cached response"
    assert response2.additional_kwargs.get('cache_hit'), "second call should be cache hit"

    print("  cached llm wrapper tests passed")


if __name__ == "__main__":
    print("running worm cache tests...\n")

    test_worm_cache_basic()
    test_worm_cache_get_or_compute()
    test_cache_persistence()
    test_cached_llm_wrapper()

    print("\nall tests passed!")
    print("\nworm cache system is working correctly and ready to replace seeded llm system")
