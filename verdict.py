"""Parse the classifier's reply into a validated verdict.

The model is asked to answer exactly ``VIOLATION|<severity 1-4>|<reason>``.
Anything else — a different prefix, a missing field, a severity outside the
ladder, an empty reason, extra lines — is rejected (``None``), never clamped or
guessed at (gameplan D1, INVARIANT-02). A ``None`` verdict means "a human should
look", not "no violation".
"""

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
