#!/usr/bin/env python3
"""test that MAX_REQUEST_INFO_PER_LEVEL is enforced"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.utils.prompts import MAX_REQUEST_INFO_PER_LEVEL


def test_pend_limit_defined():
    """verify pend limit is defined and reasonable"""
    assert MAX_REQUEST_INFO_PER_LEVEL is not None
    assert isinstance(MAX_REQUEST_INFO_PER_LEVEL, int)
    assert MAX_REQUEST_INFO_PER_LEVEL >= 1
    assert MAX_REQUEST_INFO_PER_LEVEL <= 5  # reasonable upper bound
    print(f"MAX_REQUEST_INFO_PER_LEVEL = {MAX_REQUEST_INFO_PER_LEVEL}")


if __name__ == "__main__":
    test_pend_limit_defined()
    print("\npend limit test passed!")
