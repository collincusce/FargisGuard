from database import conn, cursor

DEFAULT_RULES = """
1. No harassment or hate speech
2. No spam or flooding
3. No NSFW content outside #nsfw
4. Follow Discord TOS
"""

def get_rules(guild_id):
    cursor.execute("SELECT content FROM rules WHERE guild_id=?", (guild_id,))
    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO rules VALUES (?,?)",
        (guild_id, DEFAULT_RULES)
    )
    conn.commit()
    return DEFAULT_RULES

def set_rules(guild_id, content):
    cursor.execute(
        "REPLACE INTO rules VALUES (?,?)",
        (guild_id, content)
    )
    conn.commit()
