import pytest

from verdict import Verdict, parse_verdict


@pytest.mark.parametrize(
    "text, expected",
    [
        ("VIOLATION|1|spam", Verdict(1, "spam")),
        ("VIOLATION|4|hate speech", Verdict(4, "hate speech")),
        ("  VIOLATION | 2 | flooding  ", Verdict(2, "flooding")),
        ("VIOLATION|3|reason with | pipes | inside", Verdict(3, "reason with | pipes | inside")),
    ],
)
def test_valid_verdicts(text, expected):
    assert parse_verdict(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "Looks fine to me.",
        "violation|2|lowercase tag",
        "VIOLATION",
        "VIOLATION|2",
        "VIOLATION|2|",
        "VIOLATION||no severity",
        "VIOLATION|0|below ladder",
        "VIOLATION|5|above ladder",
        "VIOLATION|-1|negative",
        "VIOLATION|2.0|float",
        "VIOLATION|two|word",
        "VIOLATION|9999999999|huge",
        "VIOLATION|2|spam\nand a second line",
        "WARNING|2|wrong tag",
    ],
)
def test_malformed_verdicts_are_rejected(text):
    assert parse_verdict(text) is None


def test_verdict_is_frozen():
    v = parse_verdict("VIOLATION|1|x")
    with pytest.raises(AttributeError):
        v.severity = 4  # type: ignore[misc]
