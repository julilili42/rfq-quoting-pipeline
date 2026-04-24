"""Robust JSON extraction from LLM output."""
from __future__ import annotations


def extract_json_object(raw: str) -> str:
    """Return the first balanced top-level JSON object in raw.

    Handles: leading prose, markdown code fences, trailing explanations.
    Uses brace counting (not regex) so nested structures work correctly.
    """
    s = raw.strip()

    # Strip code fences (```json ... ``` or ``` ... ```)
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()

    start = s.find("{")
    if start < 0:
        raise ValueError("No JSON object found in LLM output")

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    raise ValueError("Unbalanced JSON object in LLM output")
