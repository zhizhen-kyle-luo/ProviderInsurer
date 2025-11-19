#!/usr/bin/env python3
"""integration test to verify worm cache works with game_runner"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.utils.worm_cache import WORMCache
from src.utils.cached_llm import CachedLLM


def test_cached_llm_integration():
    """test that cached llm wrapper works correctly"""
    print("testing cached llm integration...")

    # mock llm class
    class MockLLM:
        def __init__(self):
            self.call_count = 0
            self.model_name = "mock-gpt-4"

        def invoke(self, messages, **kwargs):
            self.call_count += 1

            class MockResponse:
                def __init__(self, content):
                    self.content = content

            return MockResponse(f"mock response {self.call_count}")

    # create mock message
    class MockMessage:
        def __init__(self, content):
            self.content = content

    cache = WORMCache(cache_dir=".test_integration_cache", enable_persistence=False)
    mock_llm = MockLLM()
    cached_llm = CachedLLM(mock_llm, cache, agent_name="provider")

    # first call should invoke underlying llm
    messages = [MockMessage("test prompt 1")]
    response1 = cached_llm.invoke(messages)

    assert mock_llm.call_count == 1, "should call underlying llm"
    assert response1.content == "mock response 1"
    assert response1.additional_kwargs.get('cache_hit') == False, "first call should miss cache"

    # second call with same messages should use cache
    response2 = cached_llm.invoke(messages)

    assert mock_llm.call_count == 1, "should not call underlying llm again"
    assert response2.content == "mock response 1", "should return cached response"
    assert response2.additional_kwargs.get('cache_hit') == True, "second call should hit cache"

    # call with different messages should invoke llm
    messages2 = [MockMessage("test prompt 2")]
    response3 = cached_llm.invoke(messages2)

    assert mock_llm.call_count == 2, "should call llm for different prompt"
    assert response3.content == "mock response 2"
    assert response3.additional_kwargs.get('cache_hit') == False, "different prompt should miss cache"

    # verify cache stats
    stats = cache.get_stats()
    assert stats['cache_size'] == 2, f"should have 2 cached entries, got {stats['cache_size']}"
    assert stats['hits'] == 1, f"should have 1 cache hit, got {stats['hits']}"
    assert stats['misses'] == 2, f"should have 2 cache misses, got {stats['misses']}"

    print("  integration test passed")


def test_none_response_handling():
    """test that None responses are handled correctly"""
    print("testing none response handling...")

    class MockLLMWithNone:
        def __init__(self):
            self.model_name = "mock-model"

        def invoke(self, messages, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.content = None

            return MockResponse()

    class MockMessage:
        def __init__(self, content):
            self.content = content

    cache = WORMCache(cache_dir=".test_none_cache", enable_persistence=False)
    mock_llm = MockLLMWithNone()
    cached_llm = CachedLLM(mock_llm, cache, agent_name="test")

    messages = [MockMessage("test")]
    response = cached_llm.invoke(messages)

    # should return empty string instead of None
    assert response.content == "", f"expected empty string, got {response.content}"

    # should not cache None/empty responses
    stats = cache.get_stats()
    assert stats['cache_size'] == 0, "should not cache empty responses"

    print("  none response handling test passed")


def test_error_handling():
    """test that exceptions from llm are propagated"""
    print("testing error handling...")

    class MockLLMWithError:
        def __init__(self):
            self.model_name = "mock-model"

        def invoke(self, messages, **kwargs):
            raise ValueError("simulated llm error")

    class MockMessage:
        def __init__(self, content):
            self.content = content

    cache = WORMCache(cache_dir=".test_error_cache", enable_persistence=False)
    mock_llm = MockLLMWithError()
    cached_llm = CachedLLM(mock_llm, cache, agent_name="test")

    messages = [MockMessage("test")]

    try:
        cached_llm.invoke(messages)
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert str(e) == "simulated llm error", "should propagate exception"

    print("  error handling test passed")


if __name__ == "__main__":
    print("running integration tests...\n")

    test_cached_llm_integration()
    test_none_response_handling()
    test_error_handling()

    print("\nall integration tests passed!")
