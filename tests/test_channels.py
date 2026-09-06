from channels import is_exempt
from tests.fakes import FakeChannel


def test_channel_named_nsfw_without_the_flag_is_moderated():
    assert is_exempt(FakeChannel(name="nsfw", nsfw=False)) is False


def test_flagged_channel_is_exempt_whatever_its_name():
    assert is_exempt(FakeChannel(name="general", nsfw=True)) is True


def test_object_without_is_nsfw_is_never_exempt():
    assert is_exempt(object()) is False
