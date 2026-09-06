"""Per-guild rules text the classifier enforces."""

from database import connect

DEFAULT_RULES = """
1. No harassment or hate speech
2. No spam or flooding
3. No NSFW content outside channels Discord marks NSFW
4. Follow Discord TOS
""".strip()


def get_rules(guild_id: int) -> str:
    with connect() as conn:
        row = conn.execute("SELECT content FROM rules WHERE guild_id=?", (guild_id,)).fetchone()
        if row:
            return row["content"]
        conn.execute(
            "INSERT INTO rules (guild_id, content) VALUES (?, ?)", (guild_id, DEFAULT_RULES)
        )
        return DEFAULT_RULES


def set_rules(guild_id: int, content: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO rules (guild_id, content) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET content=excluded.content",
            (guild_id, content),
        )
