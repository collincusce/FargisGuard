"""Parse the classifier's reply into validated verdicts.

Two protocols live here. ``parse_verdict`` is the original single line,
``VIOLATION|<severity 1-4>|<reason>`` (D-001). ``parse_batch_verdicts`` is the
batch form (D-013): a JSON object with one entry per message id, produced under
``VERDICT_SCHEMA`` via structured output. In both, anything malformed is
rejected — never clamped or guessed at (INVARIANT-02) — and rejection means "a
human should look", not "no violation". In the batch form that judgement is
made per id, so one bad entry never poisons its neighbours.
"""

import json
from dataclasses import dataclass

VIOLATION_TAG = "VIOLATION"
MIN_SEVERITY = 1
MAX_SEVERITY = 4


@dataclass(frozen=True)
class Verdict:
    severity: int
    reason: str


def parse_verdict(text: str | None) -> Verdict | None:
    """Return a ``Verdict`` for a well-formed reply, else ``None``.

    Pure: no I/O, no logging. The reason may itself contain ``|``.
    """
    if not text:
        return None
    line = text.strip()
    if not line or "\n" in line or "\r" in line:
        return None
    parts = line.split("|", 2)
    if len(parts) != 3:
        return None
    tag, raw_severity, reason = (part.strip() for part in parts)
    if tag != VIOLATION_TAG:
        return None
    if not raw_severity.isdigit():  # rejects "", "-1", "2.0", "abc"
        return None
    severity = int(raw_severity)
    if not MIN_SEVERITY <= severity <= MAX_SEVERITY:
        return None
    if not reason:
        return None
    return Verdict(severity=severity, reason=reason)


# --- batch protocol (D-013) -----------------------------------------------------

OK_TAG = "OK"

# The JSON schema handed to output_config.format. Every object carries
# additionalProperties:false; no numeric or length constraints (the API strips
# them anyway) — those checks happen in parse_batch_verdicts.
VERDICT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "result": {"type": "string", "enum": [OK_TAG, VIOLATION_TAG]},
                    "severity": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "reason": {"type": "string"},
                },
                "required": ["id", "result", "severity", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Clean:
    """The message broke no rule; nothing to do."""


@dataclass(frozen=True)
class Unparseable:
    """No trustworthy verdict for this id; a human looks (INVARIANT-03)."""

    problem: str


CLEAN = Clean()
Outcome = Verdict | Clean | Unparseable


@dataclass(frozen=True)
class ParsedBatch:
    outcomes: dict[int, Outcome]  # exactly one entry per expected id
    unexpected_ids: tuple[int, ...]  # ids the model invented; ignored, but logged by callers


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _entry_outcome(entry: object) -> Outcome:
    """Validate one entry the way parse_verdict validates one line."""
    if not isinstance(entry, dict):
        return Unparseable("entry is not an object")
    result = entry.get("result")
    if result == OK_TAG:
        return CLEAN
    if result != VIOLATION_TAG:
        return Unparseable(f"unknown result {result!r}")
    severity = entry.get("severity")
    if not _is_int(severity) or not MIN_SEVERITY <= severity <= MAX_SEVERITY:
        return Unparseable(f"severity {severity!r} outside {MIN_SEVERITY}..{MAX_SEVERITY}")
    reason = entry.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason:
        return Unparseable("empty reason")
    return Verdict(severity=severity, reason=reason)


def parse_batch_verdicts(text: str | None, expected_ids: list[int]) -> ParsedBatch:
    """Pure: one ``Outcome`` per expected id, failing closed per id.

    A reply that is missing, empty, not JSON, or not shaped like the schema
    makes every expected id ``Unparseable``. An id that appears twice is
    ``Unparseable`` ("duplicate"), one that never appears is ``Unparseable``
    ("missing"), and ids the model made up are reported, never applied.
    """
    expected = list(dict.fromkeys(expected_ids))
    entries: list[object] | None = None
    problem = "no reply"
    if text and text.strip():
        try:
            data = json.loads(text)
        except ValueError:
            problem = "reply is not JSON"
        else:
            if isinstance(data, dict) and isinstance(data.get("verdicts"), list):
                entries = data["verdicts"]
            else:
                problem = "reply lacks a verdicts list"
    if entries is None:
        return ParsedBatch({i: Unparseable(problem) for i in expected}, ())

    seen: dict[int, Outcome] = {}
    duplicates: set[int] = set()
    unexpected: list[int] = []
    for entry in entries:
        raw_id = entry.get("id") if isinstance(entry, dict) else None
        if not _is_int(raw_id):
            continue  # nothing to attach it to; the expected id it meant stays "missing"
        if raw_id not in expected:
            unexpected.append(raw_id)
            continue
        if raw_id in seen:
            duplicates.add(raw_id)
            continue
        seen[raw_id] = _entry_outcome(entry)

    outcomes: dict[int, Outcome] = {}
    for i in expected:
        if i in duplicates:
            outcomes[i] = Unparseable("duplicate id in reply")
        elif i in seen:
            outcomes[i] = seen[i]
        else:
            outcomes[i] = Unparseable("missing from reply")
    return ParsedBatch(outcomes, tuple(unexpected))
