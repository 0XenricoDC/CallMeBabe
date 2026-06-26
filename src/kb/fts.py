"""SQLite FTS5 knowledge-base retrieval (D-07, FAQ-01, FAQ-03).

Security (T-01-SQLI / T-02-12): all queries use parameterized MATCH ? — never
f-string user text into FTS5 SQL (Pitfall 6).

FTS5 error handling: bare FTS5 reserved keywords (AND, OR, NOT) and unmatched
quotes are syntactically invalid as standalone MATCH expressions and raise
sqlite3.OperationalError. The search() method catches OperationalError and
returns [] so natural-speech queries never crash the bot (T-02-12).
This approach is preferred over pre-sanitization because:
  1. It keeps the parameterized MATCH ? security model fully intact.
  2. It handles all current and future FTS5 syntax errors uniformly.
  3. Multi-token natural language queries (e.g. "orari e prezzi") work correctly
     because FTS5 treats lowercase "e" as a regular search token, not a keyword.
"""

from __future__ import annotations

import aiosqlite


class SQLiteFTSKnowledgeBase:
    """FTS5-based knowledge-base retrieval with tenant isolation (FAQ-01, FAQ-03).

    All queries are parameterized with MATCH ? — never f-string/format user text
    into SQL (T-01-SQLI / T-02-12 / Pitfall 6).

    FTS5 natural-speech guard: OperationalError from invalid MATCH syntax (bare
    AND/OR/NOT or unmatched quotes) is caught and mapped to an empty list so the
    caller receives a graceful not-found signal rather than an exception.
    """

    def __init__(self, db_path: str = "centralino.db") -> None:
        self._db_path = db_path

    async def search(
        self, tenant_id: str, query: str, top_k: int = 3
    ) -> list[str]:
        """Return top-k text chunks matching query for this tenant (FAQ-03: tenant-scoped).

        Returns empty list when no chunks match (FAQ-02: caller handles not-found case).
        Also returns empty list if the query is syntactically invalid for FTS5 (T-02-12):
        bare FTS5 keywords (AND, OR, NOT) or unmatched quotes raise OperationalError —
        caught here so natural-speech input never crashes the bot.

        All queries parameterized — MATCH ? with WHERE tenant_id = ? (T-01-SQLI).
        """
        try:
            async with aiosqlite.connect(self._db_path) as db:
                async with db.execute(
                    """SELECT content FROM kb_chunks
                       WHERE tenant_id = ? AND kb_chunks MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (tenant_id, query, top_k),
                ) as cur:
                    rows = await cur.fetchall()
            return [r[0] for r in rows]
        except Exception:
            # FTS5 syntax error from invalid natural-speech query (T-02-12).
            # Return empty list so the caller applies the D-08 not-found fallback.
            return []
