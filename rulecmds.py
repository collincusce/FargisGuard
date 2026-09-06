"""Slash-command handlers for scoped rules — pure enough to drive from a fake.

``bot.register_commands`` binds these to the ``/rules`` group; each returns the
ephemeral reply text. Targets arrive as Discord channel objects chosen through
a channel select, so only snowflake IDs reach the database (INVARIANT-05, D1).
"""

from dataclasses import replace
from types import SimpleNamespace

from ai_engine import render_floor
from channels import ScopeChain, resolve_scope
from composer import compose_rules
from rules import (
    CATEGORY,
    CHANNEL,
    THREAD,
    clear_scope_rules,
    set_scope_rules,
    snapshot,
)

CLEARABLE = (CATEGORY, CHANNEL, THREAD)
MAX_REPLY = 1900  # Discord's 2000-char ceiling with room for the trailer
MAX_RULES_CHARS = 4000  # a scope fragment; the composed prompt is what costs tokens


def _label(kind: str, target) -> str:
    where = getattr(target, "mention", None) or f"`{target.id}`"
    return {
        CATEGORY: f"category {where}",
        CHANNEL: f"channel {where}",
        THREAD: f"threads of {where}",
    }[kind]


def set_reply(guild_id: int, kind: str, target, content: str) -> str:
    """Store ``content`` at (kind, target.id) and say what changed."""
    text = content.strip()
    if not text:
        return "Nothing stored — send some rules text, or use `/rules clear`."
    if len(text) > MAX_RULES_CHARS:
        return f"Too long — keep one scope's rules under {MAX_RULES_CHARS} characters."
    version = set_scope_rules(guild_id, kind, target.id, text)
    return f"📜 Rules for {_label(kind, target)} updated (rules version {version})."


def clear_reply(guild_id: int, kind: str, target) -> str:
    if kind not in CLEARABLE:
        return "Choose category, channel, or thread. Server rules are set with `/setrules`."
    existed = clear_scope_rules(guild_id, kind, target.id)
    what = _label(kind, target)
    return f"🧹 Rules for {what} cleared." if existed else f"No rules were set for {what}."


def chain_for(guild, channel, *, in_thread: bool = False) -> ScopeChain:
    """The ScopeChain a message in ``channel`` would resolve to (a thread object or flag)."""
    chain = resolve_scope(SimpleNamespace(guild=guild, channel=channel))
    return replace(chain, in_thread=True) if in_thread else chain


def show_reply(guild, channel, *, in_thread: bool = False) -> str:
    """Exactly the rules text the classifier sees for ``channel``, floor included."""
    chain = chain_for(guild, channel, in_thread=in_thread)
    _, fragments = snapshot(chain.guild_id)
    resolved = compose_rules(chain, fragments)
    where = getattr(channel, "mention", None) or f"`{channel.id}`"
    suffix = " (inside its threads)" if chain.in_thread else ""
    body = f"{render_floor()}\n\n{resolved.text}"
    if len(body) > MAX_REPLY:
        body = body[: MAX_REPLY - 15] + "\n…(truncated)"
    head = f"**Effective rules for {where}{suffix}** — ruleset `{resolved.key[:12]}`"
    return f"{head}\n```\n{body}\n```"
