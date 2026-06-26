"""SQLite FTS5 knowledge-base retrieval (D-07, FAQ-01, FAQ-03).

Security (T-01-SQLI): all queries use parameterized MATCH ? — never f-string user text
into FTS5 SQL. FTS5 sanitizes the bound parameter (RESEARCH §Pitfall 6).

Wave 0 stub — full implementation in Plan 02-04.
"""

from __future__ import annotations

import aiosqlite


class SQLiteFTSKnowledgeBase:
    """FTS5-based knowledge-base retrieval with tenant isolation (FAQ-01, FAQ-03).

    Wave 0 stub: class structure and source assertions present;
    full implementation in Plan 02-04.
    """

    def __init__(self, db_path: str = "centralino.db") -> None:
        self._db_path = db_path

    async def search(
        self, tenant_id: str, query: str, top_k: int = 3
    ) -> list[str]:
        """Return top-k text chunks matching query for this tenant (FAQ-03: tenant-scoped).

        Returns empty list when no chunks match (FAQ-02: caller handles not-found case).
        All queries parameterized — MATCH ? with WHERE tenant_id = ? (T-01-SQLI).
        """
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                """SELECT content FROM kb_chunks
                   WHERE tenant_id = ? AND kb_chunks MATCH ?
                   ORDER BY rank LIMIT ?""",
                (tenant_id, query, top_k),
            ) as cur:
                rows = await cur.fetchall()
        return [r[0] for r in rows]
