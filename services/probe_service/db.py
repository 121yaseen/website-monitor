from datetime import datetime

import aiosqlite

from services.probe_service.models import ProbeResponse, ProbeResult


class DBObject:
    connection_string: str

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    @staticmethod
    async def get_db_object(connection_string: str) -> "DBObject":
        db = DBObject(connection_string)
        await db.init_db()
        return db

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.connection_string) as db:
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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS monitors (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """)
            await db.commit()

    async def get_active_monitors(self) -> list[tuple[str, str]]:
        """Return list of (id, url) for all active (non-paused) monitors."""
        async with aiosqlite.connect(self.connection_string) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, url FROM monitors WHERE is_active = 1"
            )
            rows = await cursor.fetchall()
            return [(row["id"], row["url"]) for row in rows]

    async def save_result(self, result: ProbeResult) -> None:
        if result.response is None:
            raise ValueError("Cannot save a ProbeResult with no response")

        async with aiosqlite.connect(self.connection_string) as db:
            await db.execute(
                """
                INSERT INTO probe_results (probe_id, timestamp, url, status_code,
                                        status, latency, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result.probe_id,
                    result.response.timestamp.isoformat(),
                    str(result.response.target_url),
                    result.response.status_code,
                    result.response.status,
                    result.response.latency,
                    result.response.error,
                ),
            )
            await db.commit()

    async def get_results(self, probe_id: str) -> list[ProbeResponse]:
        async with aiosqlite.connect(self.connection_string) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM probe_results WHERE probe_id = ?", (probe_id,))
            results = list(await cursor.fetchall())
            if not results:
                return []
            response = ProbeResponse(
                target_url=results[0]["url"],
                status_code=results[0]["status_code"],
                status=results[0]["status"],
                latency=results[0]["latency"],
                error=results[0]["error"],
                timestamp=datetime.fromisoformat(results[0]["timestamp"]),
            )
            return [response]
