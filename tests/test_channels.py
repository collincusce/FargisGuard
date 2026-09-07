from channels import is_exempt
from tests.fakes import FakeChannel


def test_channel_named_nsfw_without_the_flag_is_moderated():
    assert is_exempt(FakeChannel(name="nsfw", nsfw=False)) is False


def test_flagged_channel_is_exempt_whatever_its_name():
    assert is_exempt(FakeChannel(name="general", nsfw=True)) is True


def test_object_without_is_nsfw_is_never_exempt():
    assert is_exempt(object()) is False


# --- resolve_scope (gameplan D-009 / D-010) -------------------------------------

import pytest  # noqa: E402

from channels import ScopeChain, ScopeError, resolve_scope  # noqa: E402
from tests.fakes import FakeGuild, FakeMessage, FakeThread  # noqa: E402


def test_channel_in_a_category():
    msg = FakeMessage(guild=FakeGuild(id=1), channel=FakeChannel(id=10, category_id=3))
    assert resolve_scope(msg) == ScopeChain(1, 3, 10, False)


def test_channel_outside_any_category_is_normal_not_an_error():
    msg = FakeMessage(guild=FakeGuild(id=1), channel=FakeChannel(id=10, category_id=None))
    assert resolve_scope(msg) == ScopeChain(1, None, 10, False)


def test_thread_keys_on_its_parent_channel():
    parent = FakeChannel(id=10, category_id=3)
    msg = FakeMessage(guild=FakeGuild(id=1, channels={10: parent}), channel=FakeThread(70, 10))
    assert resolve_scope(msg) == ScopeChain(1, 3, 10, True)


def test_forum_post_is_a_thread_of_the_forum_channel():
    # A ForumChannel exposes category_id like any guild channel; posts are threads of it (D3).
    forum = FakeChannel(id=20, category_id=None, name="forum")
    msg = FakeMessage(guild=FakeGuild(id=1, channels={20: forum}), channel=FakeThread(71, 20))
    assert resolve_scope(msg) == ScopeChain(1, None, 20, True)


def test_dangling_parent_raises_never_falls_back():
    msg = FakeMessage(guild=FakeGuild(id=1, channels={}), channel=FakeThread(70, 10))
    with pytest.raises(ScopeError):
        resolve_scope(msg)


def test_dm_raises():
    with pytest.raises(ScopeError):
        resolve_scope(FakeMessage(guild=None))


def test_resolver_never_reads_a_name():
    class Nameless:
        id = 10
        category_id = None

        @property
        def name(self):  # pragma: no cover - the assertion is that this never runs
            raise AssertionError("resolver read .name")

    msg = FakeMessage(guild=FakeGuild(id=1), channel=Nameless())
    assert resolve_scope(msg).channel_id == 10


def test_scope_chain_is_hashable_for_memoisation():
    assert len({ScopeChain(1, None, 2, False), ScopeChain(1, None, 2, False)}) == 1
