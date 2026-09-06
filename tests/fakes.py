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
class FakeChannel:
    name: str = "general"
    nsfw: bool = False
    id: int = 500
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
    members: dict[int, object] = field(default_factory=dict)
    bans: list[tuple[int, str | None]] = field(default_factory=list)

    def get_member(self, user_id: int):
        return self.members.get(user_id)

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
    channel: FakeChannel = field(default_factory=FakeChannel)
    deleted: bool = False
    delete_forbidden: bool = False
    jump_url: str = "https://discord.com/channels/1001/500/9000"

    async def delete(self) -> None:
        if self.delete_forbidden:
            raise forbidden("Missing Permissions")
        self.deleted = True


class FakeCompletions:
    """Stands in for client.chat.completions; records every create() call."""

    def __init__(self, reply: str = "OK", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeOpenAI:
    def __init__(self, reply: str = "OK", error: Exception | None = None):
        self.completions = FakeCompletions(reply, error)
        self.chat = SimpleNamespace(completions=self.completions)
