import sqlite3

conn = sqlite3.connect("moderation.db", check_same_thread=False)
cursor = conn.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS warnings (
    user_id INTEGER,
    guild_id INTEGER,
    count INTEGER,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS rules (
    guild_id INTEGER PRIMARY KEY,
    content TEXT
);

CREATE TABLE IF NOT EXISTS appeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    guild_id INTEGER,
    reason TEXT,
    status TEXT
);
""")

conn.commit()

def add_warning(user_id, guild_id):
    cursor.execute(
        "SELECT count FROM warnings WHERE user_id=? AND guild_id=?",
        (user_id, guild_id)
    )
    row = cursor.fetchone()
    count = row[0] + 1 if row else 1

    cursor.execute(
        "REPLACE INTO warnings VALUES (?,?,?)",
        (user_id, guild_id, count)
    )
    conn.commit()
    return count

def forgive(user_id, guild_id):
    cursor.execute(
        "DELETE FROM warnings WHERE user_id=? AND guild_id=?",
        (user_id, guild_id)
    )
    conn.commit()

def get_warnings(user_id, guild_id):
    cursor.execute(
        "SELECT count FROM warnings WHERE user_id=? AND guild_id=?",
        (user_id, guild_id)
    )
    row = cursor.fetchone()
    return row[0] if row else 0
