from datetime import datetime

import aiosqlite

from services.api_service.models import LatestResult, Monitor, MonitorWithStatus, new_monitor_id


class APIDBObject:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    @staticmethod
    async def get_db_object(connection_string: str) -> "APIDBObject":
        db = APIDBObject(connection_string)
        await db.init_db()
        return db

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.connection_string) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS monitors (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL UNIQUE,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS probe_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    probe_id TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    url TEXT NOT NULL,
                    status_code INTEGER,
                    status TEXT,
                    latency REAL,
                    error TEXT
                )
            """)
            await db.commit()

    async def add_monitor(self, url: str) -> Monitor:
        monitor_id = new_monitor_id()
        created_at = datetime.now().isoformat()
        async with aiosqlite.connect(self.connection_string) as db:
            await db.execute(
                "INSERT INTO monitors (id, url, is_active, created_at) VALUES (?, ?, 1, ?)",
                (monitor_id, url, created_at),
            )
            await db.commit()
        return Monitor(
            id=monitor_id,
            url=url,
            is_active=True,
            created_at=datetime.fromisoformat(created_at),
        )

    async def delete_monitor(self, monitor_id: str) -> bool:
        async with aiosqlite.connect(self.connection_string) as db:
            cursor = await db.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def toggle_pause(self, monitor_id: str) -> Monitor | None:
        async with aiosqlite.connect(self.connection_string) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,))
            row = await cursor.fetchone()
            if row is None:
                return None
            new_active = 0 if row["is_active"] else 1
            await db.execute(
                "UPDATE monitors SET is_active = ? WHERE id = ?", (new_active, monitor_id)
            )
            await db.commit()
        return Monitor(
            id=row["id"],
            url=row["url"],
            is_active=bool(new_active),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def save_probe_result(
        self,
        probe_id: str,
        url: str,
        status: str,
        status_code: int | None,
        latency: float,
        error: str | None,
        timestamp: datetime,
    ) -> None:
        async with aiosqlite.connect(self.connection_string) as db:
            await db.execute(
                """INSERT INTO probe_results
                   (probe_id, timestamp, url, status_code, status, latency, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (probe_id, timestamp.isoformat(), url, status_code, status, latency, error),
            )
            await db.commit()

    async def get_monitor_url(self, monitor_id: str) -> str | None:
        async with aiosqlite.connect(self.connection_string) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT url FROM monitors WHERE id = ?", (monitor_id,))
            row = await cursor.fetchone()
            return str(row["url"]) if row else None

    async def list_monitors(self) -> list[MonitorWithStatus]:
        async with aiosqlite.connect(self.connection_string) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM monitors ORDER BY created_at DESC")
            monitors = await cursor.fetchall()
            result: list[MonitorWithStatus] = []
            for m in monitors:
                history_cursor = await db.execute(
                    """SELECT status, status_code, latency, error, timestamp
                       FROM probe_results WHERE url = ?
                       ORDER BY timestamp DESC LIMIT 20""",
                    (m["url"],),
                )
                history_rows = await history_cursor.fetchall()
                history = [
                    LatestResult(
                        status=row["status"],
                        status_code=row["status_code"],
                        latency=row["latency"],
                        error=row["error"],
                        checked_at=datetime.fromisoformat(row["timestamp"]),
                    )
                    for row in history_rows
                ]
                latest = history[0] if history else None
                result.append(
                    MonitorWithStatus(
                        id=m["id"],
                        url=m["url"],
                        is_active=bool(m["is_active"]),
                        created_at=datetime.fromisoformat(m["created_at"]),
                        latest=latest,
                        history=history,
                    )
                )
        return result
