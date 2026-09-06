"""Turn a per-message severity plus history into the severity to act on."""

from verdict import MAX_SEVERITY

# Prior warnings at which the ladder steps up by one, then by two. A repeat
# offender's "minor" is not minor; the cap keeps it inside the ladder.
STEP_ONE_AT = 3
STEP_TWO_AT = 6


def effective_severity(model_severity: int, prior_warnings: int) -> int:
    """Pure. Never lower than the model's severity; capped at MAX_SEVERITY."""
    if prior_warnings >= STEP_TWO_AT:
        bump = 2
    elif prior_warnings >= STEP_ONE_AT:
        bump = 1
    else:
        bump = 0
    return min(MAX_SEVERITY, model_severity + bump)
