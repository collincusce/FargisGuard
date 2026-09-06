from database import conn, cursor


def submit_appeal(user_id, guild_id, reason):
    cursor.execute(
        "INSERT INTO appeals (user_id, guild_id, reason, status) VALUES (?,?,?,?)",
        (user_id, guild_id, reason, "pending")
    )
    conn.commit()
