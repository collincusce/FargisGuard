"""Composition and the resolved-ruleset key (gameplan D-009, Phase 4)."""

import database
import rules
from channels import ScopeChain
from composer import ResolvedRules, RulesResolver, compose_rules, scope_keys
from rules import CATEGORY, CHANNEL, DEFAULT_RULES, GUILD, THREAD, set_scope_rules

G = 9


def frag(kind, scope_id, content):
    return {"scope_kind": kind, "scope_id": scope_id, "content": content}


ROWS = [
    frag(GUILD, 0, "1. Be kind\n2. No spam"),
    frag(CATEGORY, 3, "Memes allowed."),
    frag(CHANNEL, 10, "Videos only in the root."),
    frag(THREAD, 10, "Replies are plain text."),
    frag(CHANNEL, 11, "Nudity is fine here."),
]


# --- scope selection ------------------------------------------------------------


def test_scope_keys_widest_first_and_skip_absent_scopes():
    assert scope_keys(ScopeChain(G, 3, 10, True)) == [
        (GUILD, 0),
        (CATEGORY, 3),
        (CHANNEL, 10),
        (THREAD, 10),
    ]
    assert scope_keys(ScopeChain(G, None, 10, False)) == [(GUILD, 0), (CHANNEL, 10)]


def test_thread_fragment_only_applies_inside_threads():
    root = compose_rules(ScopeChain(G, 3, 10, False), ROWS).text
    reply = compose_rules(ScopeChain(G, 3, 10, True), ROWS).text
    assert "Replies are plain text." not in root
    assert "Replies are plain text." in reply
    assert reply.index("Videos only") < reply.index("Replies are plain text.")


def test_render_order_is_fixed_regardless_of_row_order():
    a = compose_rules(ScopeChain(G, 3, 10, True), ROWS)
    b = compose_rules(ScopeChain(G, 3, 10, True), list(reversed(ROWS)))
    assert a == b
    text = a.text
    assert text.index("Server rules") < text.index("Category rules") < text.index("Channel rules")
    assert text.index("Channel rules") < text.index("Thread rules")


# --- determinism and the key ----------------------------------------------------


def test_identical_inputs_produce_identical_bytes_and_key():
    chain = ScopeChain(G, 3, 10, False)
    assert compose_rules(chain, ROWS) == compose_rules(chain, [dict(r) for r in ROWS])
    assert len(compose_rules(chain, ROWS).key) == 64


def test_meaningless_whitespace_does_not_change_the_key():
    tidy = [frag(GUILD, 0, "1. Be kind\n2. No spam")]
    messy = [frag(GUILD, 0, "  1. Be kind   \r\n2. No spam\n\n")]
    chain = ScopeChain(G, None, 1, False)
    assert compose_rules(chain, tidy).key == compose_rules(chain, messy).key


def test_channels_that_inherit_the_same_text_share_a_key():
    # Neither channel 20 nor 21 has its own row; both sit in category 3.
    left = compose_rules(ScopeChain(G, 3, 20, False), ROWS)
    right = compose_rules(ScopeChain(G, 3, 21, False), ROWS)
    assert left.key == right.key
    # A channel with its own row is a different ruleset.
    assert compose_rules(ScopeChain(G, 3, 11, False), ROWS).key != left.key


def test_empty_fragments_are_omitted_not_rendered_as_headings():
    rows = [frag(GUILD, 0, "rules"), frag(CHANNEL, 10, "   \n")]
    text = compose_rules(ScopeChain(G, None, 10, False), rows).text
    assert "Channel rules" not in text


# --- memo + invalidation (real SQLite through rules.snapshot) -------------------


def test_snapshot_seeds_the_default_guild_row_and_reports_its_version():
    version, fragments = rules.snapshot(G)
    assert version == 1
    assert fragments == [{"scope_kind": GUILD, "scope_id": 0, "content": DEFAULT_RULES}]
    assert rules.get_rules(G) == DEFAULT_RULES  # no double seeding
    assert rules.get_rules_version(G) == 1


def test_resolver_memoises_until_a_write_bumps_the_version():
    calls = []

    def counting_snapshot(guild_id):
        calls.append(guild_id)
        return rules.snapshot(guild_id)

    r = RulesResolver(snapshot=counting_snapshot)
    chain = ScopeChain(G, None, 10, False)

    first = r.resolve(chain)
    assert DEFAULT_RULES.splitlines()[0] in first.text and calls == [G]
    assert r.resolve(chain) is first and calls == [G]  # hit

    set_scope_rules(G, CHANNEL, 10, "Videos only.")  # any write bumps the version
    second = r.resolve(chain)
    assert "Videos only." in second.text and calls == [G, G]
    assert second.key != first.key

    rules.clear_scope_rules(G, CATEGORY, 999)  # a no-op delete still bumps
    r.resolve(chain)
    assert calls == [G, G, G]


def test_uncached_chain_opens_exactly_one_connection(monkeypatch):
    rules.snapshot(G)  # warm guild: seeding already happened
    opened = []
    real_connect = database.connect

    def counting_connect(path=None):
        opened.append(1)
        return real_connect(path)

    monkeypatch.setattr(rules, "connect", counting_connect)
    r = RulesResolver()
    r.resolve(ScopeChain(G, None, 10, False))
    assert len(opened) == 1  # the snapshot
    r.resolve(ScopeChain(G, None, 10, False))
    assert len(opened) == 2  # the version probe on a hit


def test_forget_drops_one_guild_only():
    r = RulesResolver(snapshot=lambda g: (1, [frag(GUILD, 0, "x")]), version=lambda g: 1)
    r.resolve(ScopeChain(1, None, 1, False))
    r.resolve(ScopeChain(2, None, 1, False))
    r.forget(1)
    assert set(c.guild_id for c in r._memo) == {2}
    r.forget()
    assert r._memo == {}


def test_resolved_rules_is_a_frozen_value():
    rr = ResolvedRules(text="t", key="k")
    assert rr == ResolvedRules("t", "k") and hash(rr)
