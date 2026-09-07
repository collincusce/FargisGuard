"""Offline stand-ins for discord.py objects (INVARIANT-04).

Each fake records the calls the code under test makes, so tests assert on
behavior without a gateway connection.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace

import discord


def forbidden(message: str = "Missing Access") -> discord.Forbidden:
    """A discord.Forbidden that can be raised without a real HTTP response."""
    return discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), message)


@dataclass
class FakePermissions:
    administrator: bool = False
    manage_messages: bool = False
    manage_guild: bool = False
    ban_members: bool = False


@dataclass
class FakeRole:
    id: int
    name: str = "role"


@dataclass
class FakeCategory:
    id: int = 300
    name: str = "category"


@dataclass
class FakeChannel:
    name: str = "general"
    nsfw: bool = False
    id: int = 500
    category_id: int | None = None
    sent: list[str] = field(default_factory=list)

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    def is_nsfw(self) -> bool:
        return self.nsfw

    async def send(self, content: str) -> None:
        self.sent.append(content)


@dataclass
class FakeThread:
    """A thread is a different object from its channel in discord.py; keep that true here.

    Real ``Thread.category``/``.parent`` raise when the parent is uncached, so the
    fake deliberately offers neither — only ``parent_id`` and ``is_nsfw``.
    """

    id: int = 700
    parent_id: int = 500
    nsfw: bool = False
    sent: list[str] = field(default_factory=list)

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    def is_nsfw(self) -> bool:
        return self.nsfw

    async def send(self, content: str) -> None:
        self.sent.append(content)


@dataclass
class FakeGuild:
    id: int = 1001
    text_channels: list[FakeChannel] = field(default_factory=list)
    channels: dict[int, object] = field(default_factory=dict)
    members: dict[int, object] = field(default_factory=dict)
    bans: list[tuple[int, str | None]] = field(default_factory=list)

    def get_member(self, user_id: int):
        return self.members.get(user_id)

    def get_channel(self, channel_id: int):
        return self.channels.get(channel_id)

    async def ban(self, user, *, reason: str | None = None) -> None:
        self.bans.append((getattr(user, "id", user), reason))


@dataclass
class FakeMember:
    id: int = 42
    bot: bool = False
    guild: FakeGuild = field(default_factory=FakeGuild)
    roles: list[FakeRole] = field(default_factory=list)
    guild_permissions: FakePermissions = field(default_factory=FakePermissions)
    dms_closed: bool = False
    sent: list[str] = field(default_factory=list)
    timeouts: list[tuple[object, str | None]] = field(default_factory=list)
    kicks: list[str | None] = field(default_factory=list)
    bans: list[str | None] = field(default_factory=list)

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    async def send(self, content: str) -> None:
        if self.dms_closed:
            raise forbidden("Cannot send messages to this user")
        self.sent.append(content)

    async def timeout(self, until, *, reason: str | None = None) -> None:
        self.timeouts.append((until, reason))

    async def kick(self, *, reason: str | None = None) -> None:
        self.kicks.append(reason)

    async def ban(self, *, reason: str | None = None) -> None:
        self.bans.append(reason)


@dataclass
class FakeMessage:
    content: str = "hello"
    author: FakeMember = field(default_factory=FakeMember)
    guild: FakeGuild | None = field(default_factory=FakeGuild)
    channel: FakeChannel | FakeThread = field(default_factory=FakeChannel)
    deleted: bool = False
    delete_forbidden: bool = False
    jump_url: str = "https://discord.com/channels/1001/500/9000"

    async def delete(self) -> None:
        if self.delete_forbidden:
            raise forbidden("Missing Permissions")
        self.deleted = True


class FakeMessages:
    """Stands in for client.messages; records every create() call (INVARIANT-06)."""

    def __init__(
        self,
        reply: str = "",
        error: Exception | None = None,
        stop_reason: str = "end_turn",
        usage=None,
    ):
        self.reply = reply  # the text of the first content block (JSON under structured output)
        self.error = error
        self.stop_reason = stop_reason
        self.usage = usage  # e.g. SimpleNamespace(input_tokens=..., output_tokens=..., ...)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.reply)],
            stop_reason=self.stop_reason,
            usage=self.usage,
        )


class FakeAnthropic:
    def __init__(
        self,
        reply: str = "",
        error: Exception | None = None,
        stop_reason: str = "end_turn",
        usage=None,
    ):
        self.messages = FakeMessages(reply, error, stop_reason, usage)


def batch_reply(*entries: dict) -> str:
    """A structured-output reply body for the given verdict entries."""
    import json

    return json.dumps({"verdicts": list(entries)})


def ok_entry(i: int) -> dict:
    return {"id": i, "result": "OK", "severity": None, "reason": ""}


def violation_entry(i: int, severity: int, reason: str) -> dict:
    return {"id": i, "result": "VIOLATION", "severity": severity, "reason": reason}


@dataclass
class FakeResponse:
    sent: list[tuple[str, bool]] = field(default_factory=list)

    async def send_message(self, content: str, *, ephemeral: bool = False) -> None:
        self.sent.append((content, ephemeral))


@dataclass
class FakeInteraction:
    """Enough of discord.Interaction to drive a slash-command callback offline."""

    user: FakeMember = field(default_factory=FakeMember)
    guild: FakeGuild = field(default_factory=FakeGuild)
    response: FakeResponse = field(default_factory=FakeResponse)

    @property
    def guild_id(self) -> int:
        return self.guild.id

    @property
    def permissions(self) -> FakePermissions:
        """What app_commands.checks.has_permissions reads."""
        return self.user.guild_permissions
