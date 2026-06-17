import json
import aiosqlite

DB_PATH = "botdata.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    log_channel_id INTEGER,
    mute_role_id INTEGER,
    autorole_id INTEGER,
    ticket_category_id INTEGER,
    ticket_log_channel_id INTEGER,
    ticket_support_role_id INTEGER,
    ticket_counter INTEGER DEFAULT 0,
    antinuke_enabled INTEGER DEFAULT 1,
    application_panel_channel_id INTEGER,
    application_log_channel_id INTEGER,
    application_accepted_role_id INTEGER,
    application_questions TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS antinuke_whitelist (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS self_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    label TEXT,
    emoji TEXT,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT DEFAULT 'open',
    created_at TEXT
);
"""

_DEFAULT_COLUMNS = [
    "log_channel_id", "mute_role_id", "autorole_id", "ticket_category_id",
    "ticket_log_channel_id", "ticket_support_role_id", "ticket_counter",
    "antinuke_enabled", "application_panel_channel_id",
    "application_log_channel_id", "application_accepted_role_id",
    "application_questions",
]


class Database:
    def __init__(self, connection: aiosqlite.Connection):
        self.conn = connection

    # ---------- guild settings ----------
    async def ensure_guild(self, guild_id: int):
        await self.conn.execute(
            "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
        )
        await self.conn.commit()

    async def get_settings(self, guild_id: int) -> dict:
        await self.ensure_guild(guild_id)
        cur = await self.conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        data["application_questions"] = json.loads(data["application_questions"] or "[]")
        return data

    async def update_settings(self, guild_id: int, **kwargs):
        await self.ensure_guild(guild_id)
        if "application_questions" in kwargs and not isinstance(kwargs["application_questions"], str):
            kwargs["application_questions"] = json.dumps(kwargs["application_questions"])
        keys = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [guild_id]
        await self.conn.execute(
            f"UPDATE guild_settings SET {keys} WHERE guild_id = ?", values
        )
        await self.conn.commit()

    async def increment_ticket_counter(self, guild_id: int) -> int:
        settings = await self.get_settings(guild_id)
        new_value = (settings["ticket_counter"] or 0) + 1
        await self.update_settings(guild_id, ticket_counter=new_value)
        return new_value

    # ---------- warns ----------
    async def add_warn(self, guild_id: int, user_id: int, moderator_id: int, reason: str, timestamp: str):
        await self.conn.execute(
            "INSERT INTO warns (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, timestamp),
        )
        await self.conn.commit()

    async def get_warns(self, guild_id: int, user_id: int) -> list:
        cur = await self.conn.execute(
            "SELECT id, moderator_id, reason, timestamp FROM warns WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        )
        rows = await cur.fetchall()
        return [
            {"id": r[0], "moderator_id": r[1], "reason": r[2], "timestamp": r[3]}
            for r in rows
        ]

    async def clear_warns(self, guild_id: int, user_id: int):
        await self.conn.execute(
            "DELETE FROM warns WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        await self.conn.commit()

    # ---------- anti-nuke whitelist ----------
    async def add_whitelist(self, guild_id: int, user_id: int):
        await self.conn.execute(
            "INSERT OR IGNORE INTO antinuke_whitelist (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        await self.conn.commit()

    async def remove_whitelist(self, guild_id: int, user_id: int):
        await self.conn.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.conn.commit()

    async def is_whitelisted(self, guild_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "SELECT 1 FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return (await cur.fetchone()) is not None

    async def get_whitelist(self, guild_id: int) -> list:
        cur = await self.conn.execute(
            "SELECT user_id FROM antinuke_whitelist WHERE guild_id = ?", (guild_id,)
        )
        return [r[0] for r in await cur.fetchall()]

    # ---------- self roles ----------
    async def add_self_role(self, guild_id: int, role_id: int, label: str, emoji: str):
        await self.conn.execute(
            "INSERT OR REPLACE INTO self_roles (guild_id, role_id, label, emoji) VALUES (?, ?, ?, ?)",
            (guild_id, role_id, label, emoji),
        )
        await self.conn.commit()

    async def remove_self_role(self, guild_id: int, role_id: int):
        await self.conn.execute(
            "DELETE FROM self_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)
        )
        await self.conn.commit()

    async def get_self_roles(self, guild_id: int) -> list:
        cur = await self.conn.execute(
            "SELECT role_id, label, emoji FROM self_roles WHERE guild_id = ?", (guild_id,)
        )
        rows = await cur.fetchall()
        return [{"role_id": r[0], "label": r[1], "emoji": r[2]} for r in rows]

    async def get_all_guilds_with_self_roles(self) -> list:
        cur = await self.conn.execute("SELECT DISTINCT guild_id FROM self_roles")
        return [r[0] for r in await cur.fetchall()]

    # ---------- tickets ----------
    async def create_ticket(self, channel_id: int, guild_id: int, user_id: int, created_at: str):
        await self.conn.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id, status, created_at) VALUES (?, ?, ?, 'open', ?)",
            (channel_id, guild_id, user_id, created_at),
        )
        await self.conn.commit()

    async def close_ticket(self, channel_id: int):
        await self.conn.execute(
            "UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (channel_id,)
        )
        await self.conn.commit()

    async def get_ticket(self, channel_id: int):
        cur = await self.conn.execute(
            "SELECT channel_id, guild_id, user_id, status, created_at FROM tickets WHERE channel_id = ?",
            (channel_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {"channel_id": row[0], "guild_id": row[1], "user_id": row[2], "status": row[3], "created_at": row[4]}


async def init_db() -> Database:
    conn = await aiosqlite.connect(DB_PATH)
    await conn.executescript(_SCHEMA)
    await conn.commit()
    return Database(conn)
