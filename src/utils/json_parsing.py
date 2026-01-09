"""
robust JSON extraction from LLM responses

handles common LLM output patterns:
- conversational filler ("Here is the JSON: ...")
- code blocks with/without language markers
- trailing commas and comments
"""
import json
import re
from typing import Dict, Any


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    extract JSON from LLM response that may contain conversational filler

    strategies (in order):
    1. extract from ```json...``` code blocks
    2. extract from ```...``` code blocks
    3. find first { to last } and extract
    4. cleanup common errors and retry

    raises:
        ValueError: if JSON cannot be extracted/parsed, with diagnostic info
    """
    if not text or not isinstance(text, str):
        raise ValueError(f"invalid input: expected non-empty string, got {type(text)}")

    original_text = text

    # strategy 1: ```json ... ``` code blocks
    json_block_pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(json_block_pattern, text, re.DOTALL)
    if matches:
        text = matches[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # try cleanup before giving up
            text = _cleanup_json_errors(text)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass  # continue to next strategy

    # strategy 2: generic ``` ... ``` code blocks
    generic_block_pattern = r'```\s*(.*?)\s*```'
    matches = re.findall(generic_block_pattern, original_text, re.DOTALL)
    if matches:
        text = matches[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            text = _cleanup_json_errors(text)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

    # strategy 3: find first { to last }
    first_brace = original_text.find('{')
    last_brace = original_text.rfind('}')

    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = original_text[first_brace:last_brace + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # try cleanup
            text = _cleanup_json_errors(text)
            try:
                return json.loads(text)
            except json.JSONDecodeError as final_error:
                # all strategies failed - raise detailed error
                snippet = text[:200] + "..." if len(text) > 200 else text
                raise ValueError(
                    f"failed to parse JSON after all strategies.\n"
                    f"final error: {str(final_error)}\n"
                    f"extracted text snippet: {snippet}"
                )

    # no JSON structure found at all
    snippet = original_text[:200] + "..." if len(original_text) > 200 else original_text
    raise ValueError(
        f"no JSON structure found in LLM response.\n"
        f"response snippet: {snippet}"
    )


def _cleanup_json_errors(text: str) -> str:
    """
    cleanup common JSON errors from LLM outputs
    - trailing commas before } or ]
    - single-line comments
    """
    # remove trailing commas before closing braces/brackets
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)

    # remove single-line comments (// ...)
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)

    return text