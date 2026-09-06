import pytest

from config import ConfigError, parse_id_list


def test_parse_id_list_handles_blanks_and_spaces():
    assert parse_id_list(" 1, 22 ,,333 , ") == frozenset({1, 22, 333})


def test_parse_id_list_empty_is_empty():
    assert parse_id_list("") == frozenset()


def test_parse_id_list_rejects_non_integers_naming_the_variable():
    with pytest.raises(ConfigError, match="IMMUNE_ROLE_IDS"):
        parse_id_list("1,Moderator", name="IMMUNE_ROLE_IDS")
