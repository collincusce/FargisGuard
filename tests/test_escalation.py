import pytest

from escalation import STEP_ONE_AT, STEP_TWO_AT, effective_severity


@pytest.mark.parametrize(
    "severity, priors, expected",
    [
        (1, 0, 1),
        (1, 2, 1),
        (1, 3, 2),
        (1, 5, 2),
        (1, 6, 3),
        (2, 3, 3),
        (2, 6, 4),
        (3, 6, 4),  # capped
        (4, 0, 4),
        (4, 99, 4),
    ],
)
def test_ladder(severity, priors, expected):
    assert effective_severity(severity, priors) == expected


def test_never_lowers_the_model_severity():
    for s in range(1, 5):
        assert effective_severity(s, 0) == s


def test_thresholds_are_documented_constants():
    assert STEP_ONE_AT < STEP_TWO_AT
