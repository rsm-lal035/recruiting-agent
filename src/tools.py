"""
Small tools used by the pipeline.

  - validate_boolean_query: Bonus item — a deterministic check the agent runs
    after Step 3, like a function-calling tool. Catches the most common failures
    (unbalanced parens, no operators) that an LLM can produce confidently-but-wrong.

  - check_outreach_for_bias: Bonus guardrail — flags outreach messages containing
    age, gender, or other protected-characteristic language. See README for the
    reasoning on WHY this output specifically needs a guardrail.
"""

from __future__ import annotations

import re


# Boolean query validator
def validate_boolean_query(query: str) -> dict:
    """
    Deterministic checks on a Boolean sourcing query.
    Returns a dict the pipeline can log + attach to output.
    """
    warnings: list[str] = []

    if not query or not query.strip():
        return {
            "is_valid": False,
            "balanced_parens": False,
            "has_and": False,
            "has_or": False,
            "warning": "empty query",
        }

    # Parens balance
    balanced = query.count("(") == query.count(")")
    if not balanced:
        warnings.append("unbalanced parentheses")

    # Operators — use word boundaries to avoid matching 'and' inside words.
    has_and = bool(re.search(r"\bAND\b", query))
    has_or = bool(re.search(r"\bOR\b", query))
    if not has_and and not has_or:
        warnings.append("no AND/OR operators found — query may be too narrow")

    # Quote balance (straight double quotes only).
    if query.count('"') % 2 != 0:
        warnings.append("unbalanced double quotes")

    # Length sanity check — queries that are too long get rejected by most platforms.
    if len(query) > 1000:
        warnings.append(f"query is {len(query)} chars; many platforms cap at ~1000")

    is_valid = not warnings

    return {
        "is_valid": is_valid,
        "balanced_parens": balanced,
        "has_and": has_and,
        "has_or": has_or,
        "length": len(query),
        "warning": "; ".join(warnings) if warnings else "",
    }


# Outreach bias guardrail
# Heuristic patterns for language that would be inappropriate in recruiting outreach.
# This is intentionally narrow — flagging false positives is better than missing real ones,
# and a human reviews the flag.
_BIAS_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "age-coded language",
        re.compile(
            r"\b(young|youthful|energetic|digital native|recent grad|seasoned veteran)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "gendered pronouns/terms",
        re.compile(r"\b(guys|brotherhood|salesman|salesmen|manpower)\b", re.IGNORECASE),
    ),
    ("'culture fit' language", re.compile(r"\bculture fit\b", re.IGNORECASE)),
    (
        "compensation/salary mention (premature)",
        re.compile(r"\$\d|\bsalary\b|\bequity\b|\bcomp(?:ensation)?\b", re.IGNORECASE),
    ),
]


def check_outreach_for_bias(message: str) -> str:
    """
    Returns a warning string if the message contains potentially problematic language,
    or an empty string if it looks clean. Pipeline attaches this to the trace but does NOT
    block the message — a human recruiter should make the final call.
    """
    if not message:
        return ""
    hits = []
    for label, pattern in _BIAS_PATTERNS:
        if pattern.search(message):
            hits.append(label)
    if hits:
        return f"Outreach may contain problematic language: {', '.join(hits)}. Human review recommended."
    return ""
