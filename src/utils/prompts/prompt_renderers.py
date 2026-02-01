from __future__ import annotations

from typing import Any, Dict


def render_line_summary(line: Dict[str, Any]) -> str:
    ln = line.get("line_number")
    code = line.get("procedure_code")
    ctype = line.get("code_type")
    name = line.get("service_name")
    rtype = line.get("request_type")
    qty = line.get("requested_quantity")
    return f"line={ln} type={rtype} code={code}/{ctype} name={name} qty={qty}"
