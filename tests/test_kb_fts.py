"""Tests for SQLiteFTSKnowledgeBase — FAQ retrieval and tenant isolation (FAQ-01, FAQ-02, FAQ-03).

Covers:
- faq_lookup returns top-k text chunks matching a query (FAQ-01)
- When no match exists, returns an empty list (FAQ-02 — no hallucination)
- Query for tenant A never returns tenant B's chunks (FAQ-03/T-3 — tenant isolation)
- Source-assertion: parameterized MATCH ? only, no f-string/format SQL (T-02-01)

Wave 0 state: RED — src/kb/fts.py does not exist yet.
These tests will fail with ImportError until Plan 02-04 creates the module.
"""

from __future__ import annotations

import inspect

import pytest

from src.kb.fts import SQLiteFTSKnowledgeBase  # RED: does not exist yet


async def test_faq_lookup(seeded_kb: SQLiteFTSKnowledgeBase):
    """FAQ-01: search returns top-k text chunks matching the query for the given tenant."""
    results = await seeded_kb.search(tenant_id="demo", query="orari", top_k=3)

    assert isinstance(results, list), (
        f"search must return a list; got {type(results)}"
    )
    assert len(results) > 0, (
        "search('orari') for tenant 'demo' must return at least one chunk. "
        "The seeded_kb fixture ingests a chunk containing 'Orari: lunedì chiuso...'."
    )
    # Each result must be a non-empty string (chunk content)
    for chunk in results:
        assert isinstance(chunk, str) and chunk, (
            f"Each search result must be a non-empty string; got {chunk!r}"
        )


async def test_faq_not_found(seeded_kb: SQLiteFTSKnowledgeBase):
    """FAQ-02: search returns an empty list when no chunks match the query.

    A query for a nonsense term that is not in the knowledge base must return
    an empty list — the caller handles the 'not found' case without inventing data.
    """
    results = await seeded_kb.search(
        tenant_id="demo",
        query="zxqwjkpineapplexqzw",  # guaranteed to not match anything
        top_k=3,
    )

    assert isinstance(results, list), (
        f"search must return a list even when nothing matches; got {type(results)}"
    )
    assert results == [], (
        f"search must return an empty list when no chunks match. Got: {results!r}. "
        "The KB must not invent content (FAQ-02)."
    )


async def test_tenant_isolation(seeded_kb: SQLiteFTSKnowledgeBase):
    """FAQ-03/T-3: search for tenant 'demo' must never return 'other_tenant' chunks.

    The seeded_kb fixture inserts chunks for both 'demo' and 'other_tenant'.
    A query that matches chunks in both tenants must only return 'demo' chunks.
    """
    # Query that matches content in both tenants (the word 'tenant' appears in both)
    results = await seeded_kb.search(tenant_id="demo", query="pizza", top_k=5)

    # All returned chunks must come from the demo tenant's content
    # (The other_tenant chunk contains "Pizza margherita speciale solo per l'altro tenant")
    for chunk in results:
        assert "altro tenant" not in chunk, (
            f"Tenant isolation violated: search for 'demo' returned content from "
            f"'other_tenant': {chunk!r}. "
            "All FTS5 queries must include WHERE tenant_id = ? to prevent cross-tenant leakage."
        )


async def test_faq_lookup_top_k_limit(seeded_kb: SQLiteFTSKnowledgeBase):
    """FAQ-01: search respects the top_k limit and returns at most top_k results."""
    # The seeded_kb has 3 demo chunks; requesting top_k=2 must return at most 2
    results = await seeded_kb.search(tenant_id="demo", query="euro", top_k=2)

    assert len(results) <= 2, (
        f"search must return at most top_k=2 results; got {len(results)}: {results}"
    )


def test_kb_fts_parameterized():
    """T-02-01: SQLiteFTSKnowledgeBase uses only parameterized SQL (no injection vectors).

    Source-assertion: inspect the source to confirm:
    - FTS5 queries use MATCH ? (not string interpolation)
    - No .format( into SQL strings
    - No f-string SQL containing MATCH or SELECT
    """
    source = inspect.getsource(SQLiteFTSKnowledgeBase)

    assert "MATCH ?" in source, (
        "SQLiteFTSKnowledgeBase must use parameterized MATCH ? for FTS5 queries. "
        "Never interpolate the query text directly into SQL (Pitfall 6)."
    )
    assert ".format(" not in source, (
        "SQLiteFTSKnowledgeBase must not use .format( to build SQL strings."
    )
    assert 'f"SELECT' not in source, (
        "SQLiteFTSKnowledgeBase must not use f-strings to build SELECT queries."
    )


async def test_fts5_natural_speech_no_raise(seeded_kb: SQLiteFTSKnowledgeBase):
    """T-02-12: FTS5 MATCH injection guard — natural-speech queries must never raise.

    Bare FTS5 keywords (AND, OR, NOT) and unmatched quotes are syntactically
    invalid in FTS5 MATCH expressions. search() must sanitize or catch the error
    and return an empty list rather than propagating an OperationalError.
    This prevents Pitfall-6 crashes on everyday Italian speech.
    """
    problematic_queries = [
        "AND",               # bare FTS5 keyword
        "OR",                # bare FTS5 keyword
        "NOT",               # bare FTS5 keyword
        '"',                 # unterminated quote
        '"open quote',       # unterminated quote
        "orari e prezzi",    # 'e' is not a special FTS5 keyword — should succeed
    ]
    for query in problematic_queries:
        try:
            results = await seeded_kb.search(tenant_id="demo", query=query, top_k=3)
            assert isinstance(results, list), (
                f"search({query!r}) must return a list; got {type(results)}"
            )
        except Exception as exc:
            raise AssertionError(
                f"search({query!r}) must not raise; got {type(exc).__name__}: {exc}\n"
                "Natural-speech queries must be sanitized or OperationalError caught (T-02-12)."
            ) from exc
