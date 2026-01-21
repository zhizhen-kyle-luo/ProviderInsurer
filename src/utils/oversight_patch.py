from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, List, Set, Tuple

def _parse_pointer(path: str) -> List[str]:
    """JSON Pointer (RFC 6901) path -> tokens."""
    if path == "":
        return []
    if not path.startswith("/"):
        raise ValueError(f"bad json-pointer: {path}")
    parts = path.split("/")[1:]
    return [p.replace("~1", "/").replace("~0", "~") for p in parts]

def _get_parent(doc: Any, tokens: List[str]) -> Tuple[Any, str]:
    if not tokens:
        raise ValueError("root has no parent")
    cur = doc
    for t in tokens[:-1]:
        if isinstance(cur, list):
            cur = cur[int(t)]
        else:
            cur = cur[t]
    return cur, tokens[-1]

def _paths_touched(patch: List[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    for op in patch:
        p = op.get("path")
        if isinstance(p, str):
            out.add(p)
    return out

def enforce_patch_budgets(
    patch: List[Dict[str, Any]],
    *,
    max_patch_ops: int,
    max_paths_touched: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hard clamp edits so 'low effort' literally cannot make lots of edits.
    """
    meta = {
        "patch_ops": len(patch),
        "paths_touched": len(_paths_touched(patch)),
        "max_patch_ops": max_patch_ops,
        "max_paths_touched": max_paths_touched,
        "truncated": False,
    }

    if len(patch) <= max_patch_ops and meta["paths_touched"] <= max_paths_touched:
        return patch, meta

    kept: List[Dict[str, Any]] = []
    paths: Set[str] = set()

    for op in patch:
        if len(kept) >= max_patch_ops:
            break
        p = op.get("path")
        if not isinstance(p, str):
            continue
        if p not in paths and len(paths) >= max_paths_touched:
            continue
        kept.append(op)
        paths.add(p)

    meta["truncated"] = True
    meta["patch_ops_after"] = len(kept)
    meta["paths_touched_after"] = len(paths)
    return kept, meta

def apply_json_patch(doc: Any, patch: List[Dict[str, Any]]) -> Any:
    """
    Apply subset of JSON Patch (RFC 6902): add/remove/replace.
    """
    out = deepcopy(doc)

    for op in patch:
        if not isinstance(op, dict):
            raise ValueError("patch op must be object")
        kind = op.get("op")
        path = op.get("path")
        if kind not in {"add", "remove", "replace"}:
            raise ValueError(f"unsupported op: {kind}")
        if not isinstance(path, str):
            raise ValueError("missing path")

        tokens = _parse_pointer(path)

        if not tokens:
            if kind == "remove":
                raise ValueError("refuse to remove root")
            out = deepcopy(op.get("value"))
            continue

        parent, last = _get_parent(out, tokens)

        if isinstance(parent, list):
            idx = len(parent) if last == "-" else int(last)
            if kind == "remove":
                parent.pop(idx)
            elif kind == "replace":
                parent[idx] = op.get("value")
            else:  # add
                if last == "-":
                    parent.append(op.get("value"))
                else:
                    parent.insert(idx, op.get("value"))
            continue

        # dict parent
        if kind == "remove":
            parent.pop(last, None)
        elif kind == "replace":
            if last not in parent:
                raise ValueError(f"replace missing key: {path}")
            parent[last] = op.get("value")
        else:  # add
            parent[last] = op.get("value")

    return out
