"""
robust JSON extraction from LLM responses

handles common LLM output patterns:
- conversational filler ("Here is the JSON: ...")
- code blocks with/without language markers
- trailing commas and comments
- control characters inside strings
"""
import json
import re
from typing import Any, Optional


def extract_json_from_text(text: str) -> Any:
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

    # try each extraction strategy
    extracted = _try_json_block(text) or _try_generic_block(text) or _try_brace_extraction(text)

    if extracted is None:
        snippet = text[:200] + "..." if len(text) > 200 else text
        raise ValueError(f"no JSON structure found in LLM response.\nresponse snippet: {snippet}")

    return extracted


def _try_json_block(text: str) -> Optional[Dict[str, Any]]:
    """try to extract JSON from ```json ... ``` code blocks"""
    matches = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if matches:
        return _parse_with_cleanup(matches[0].strip())
    return None


def _try_generic_block(text: str) -> Optional[Dict[str, Any]]:
    """try to extract JSON from generic ``` ... ``` code blocks"""
    matches = re.findall(r'```\s*(.*?)\s*```', text, re.DOTALL)
    if matches:
        return _parse_with_cleanup(matches[0].strip())
    return None


def _try_brace_extraction(text: str) -> Optional[Any]:
    """try to extract JSON by finding first {/[ to last }/]"""
    # try object first
    first_brace = text.find('{')
    last_brace = text.rfind('}')

    # try array
    first_bracket = text.find('[')
    last_bracket = text.rfind(']')

    # pick whichever comes first (object or array)
    use_object = first_brace != -1 and last_brace > first_brace
    use_array = first_bracket != -1 and last_bracket > first_bracket

    if use_object and use_array:
        # use whichever starts first
        if first_brace < first_bracket:
            extracted = text[first_brace:last_brace + 1]
        else:
            extracted = text[first_bracket:last_bracket + 1]
    elif use_object:
        extracted = text[first_brace:last_brace + 1]
    elif use_array:
        extracted = text[first_bracket:last_bracket + 1]
    else:
        return None

    result = _parse_with_cleanup(extracted)

    if result is None:
        snippet = extracted[:200] + "..." if len(extracted) > 200 else extracted
        raise ValueError(f"failed to parse JSON after all strategies.\nextracted text snippet: {snippet}")

    return result


def _parse_with_cleanup(text: str) -> Optional[Any]:
    """try to parse JSON, with cleanup on failure"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    cleaned = _cleanup_json_errors(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _cleanup_json_errors(text: str) -> str:
    """
    cleanup common JSON errors from LLM outputs
    - trailing commas before } or ]
    - single-line comments
    - invalid control characters inside strings (newlines, tabs)
    """
    # remove trailing commas before closing braces/brackets
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)

    # remove single-line comments (// ...) - use .* for greedy match to end of line
    text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)

    # escape control characters inside string values
    text = _escape_control_chars_in_strings(text)

    return text


def _escape_control_chars_in_strings(text: str) -> str:
    """
    escape control characters (newlines, tabs, etc.) inside JSON string values.
    LLMs often output literal newlines inside strings which breaks JSON parsing.
    """
    escape_map = {'\n': '\\n', '\r': '\\r', '\t': '\\t'}

    result = []
    in_string = False
    escape_next = False

    for char in text:
        if escape_next:
            result.append(char)
            escape_next = False
        elif char == '\\':
            result.append(char)
            escape_next = True
        elif char == '"':
            result.append(char)
            in_string = not in_string
        elif in_string:
            result.append(_escape_char(char, escape_map))
        else:
            result.append(char)

    return ''.join(result)


def _escape_char(char: str, escape_map: dict) -> str:
    """escape a single character if it's a control character"""
    if char in escape_map:
        return escape_map[char]
    if ord(char) < 32:
        return f'\\u{ord(char):04x}'
    return char
