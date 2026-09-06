"""Compose a message's scoped rules into one prompt block with a stable identity.

``compose_rules`` is pure and byte-deterministic (D-009): the same fragments in
any storage order produce the same text, and ``key`` is the sha256 of that text.
Two channels that inherit identical rules therefore share a key — which is what
the batching and prompt-caching work that follows will group on.

``RulesResolver`` memoises ``ScopeChain → ResolvedRules`` and invalidates by the
guild's rules version, so a write anywhere in the guild (including the default
seeding) is seen on the next message without any cross-module signalling.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

import rules as rules_store
from channels import ScopeChain
from rules import CATEGORY, CHANNEL, GUILD, GUILD_SCOPE_ID, THREAD

# Fixed render order: widest to narrowest. The label tells the model which is which.
SCOPE_ORDER: tuple[str, ...] = (GUILD, CATEGORY, CHANNEL, THREAD)
SCOPE_LABELS = {
    GUILD: "Server rules",
    CATEGORY: "Category rules (apply on top of the server rules)",
    CHANNEL: "Channel rules (apply on top of the above)",
    THREAD: "Thread rules (apply inside this channel's threads, on top of the above)",
}


@dataclass(frozen=True)
class ResolvedRules:
    text: str
    key: str  # sha256 hex digest of ``text``


def scope_keys(chain: ScopeChain) -> list[tuple[str, int]]:
    """Pure: the (kind, id) rows that apply to a chain, widest first."""
    keys = [(GUILD, GUILD_SCOPE_ID)]
    if chain.category_id is not None:
        keys.append((CATEGORY, chain.category_id))
    keys.append((CHANNEL, chain.channel_id))
    if chain.in_thread:
        keys.append((THREAD, chain.channel_id))
    return keys


def _normalise(content: str) -> str:
    """Whitespace that carries no meaning must not change the key."""
    lines = [line.rstrip() for line in content.replace("\r\n", "\n").strip().splitlines()]
    return "\n".join(lines)


def compose_rules(chain: ScopeChain, fragments: list[dict]) -> ResolvedRules:
    """Pure: render the applicable fragments in fixed order; hash the result."""
    by_key = {(f["scope_kind"], f["scope_id"]): f["content"] for f in fragments}
    parts = []
    for kind, scope_id in scope_keys(chain):
        content = by_key.get((kind, scope_id))
        if content is None or not content.strip():
            continue
        parts.append(f"## {SCOPE_LABELS[kind]}\n{_normalise(content)}")
    text = "\n\n".join(parts)
    return ResolvedRules(text=text, key=hashlib.sha256(text.encode("utf-8")).hexdigest())


Snapshot = Callable[[int], tuple[int, list[dict]]]
VersionProbe = Callable[[int], int]


class RulesResolver:
    """Memoised ``ScopeChain → ResolvedRules``, invalidated by the guild rules version.

    Cost per message: an uncached chain opens one connection (the snapshot);
    a cached one opens one (the version probe); a stale one opens two.
    """

    def __init__(
        self,
        *,
        snapshot: Snapshot = rules_store.snapshot,
        version: VersionProbe = rules_store.get_rules_version,
    ):
        self._snapshot = snapshot
        self._version = version
        self._memo: dict[ScopeChain, tuple[int, ResolvedRules]] = {}

    def resolve(self, chain: ScopeChain) -> ResolvedRules:
        hit = self._memo.get(chain)
        if hit is not None and hit[0] == self._version(chain.guild_id):
            return hit[1]
        version, fragments = self._snapshot(chain.guild_id)
        resolved = compose_rules(chain, fragments)
        self._memo[chain] = (version, resolved)
        return resolved

    def forget(self, guild_id: int | None = None) -> None:
        """Drop memo entries (all, or one guild's). Tests and hot reloads only."""
        if guild_id is None:
            self._memo.clear()
        else:
            for chain in [c for c in self._memo if c.guild_id == guild_id]:
                del self._memo[chain]


_resolver: RulesResolver | None = None


def get_resolver() -> RulesResolver:
    """The process-wide resolver, created on first use."""
    global _resolver
    if _resolver is None:
        _resolver = RulesResolver()
    return _resolver
