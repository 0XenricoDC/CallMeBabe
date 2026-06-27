"""Tests for CallLogRepository (NOTIF-01, D-06, D-08).

RED state (Task 1): imports from src.call_log.repository which does NOT yet
exist — tests will FAIL/ERROR until Task 2 implements it. That is the expected
RED state per TDD protocol.

Coverage:
- test_write_row_roundtrip      : written row selectable back with correct data
- test_outcome_check_constraint : invalid outcome raises IntegrityError (D-06)
- test_transcript_json_array    : transcript_json stores a JSON-serialized list
- test_determine_outcome_*      : _determine_outcome logic (Pattern 5 RESEARCH.md)
"""

from __future__ import annotations

import json
import sqlite3

import pytest


# ---------------------------------------------------------------------------
# Fixture — mirrors TenantRepository pattern from test_repository.py
# ---------------------------------------------------------------------------

@pytest.fixture
async def call_log_repo(tmp_path):
    """An initialised CallLogRepository backed by a temp-file DB.

    Uses CallLogRepository.init_db() which runs the full schema.sql (idempotent).
    The tenants table must be seeded before call_logs can reference it (FK).
    """
    from src.call_log.repository import CallLogRepository  # noqa: PLC0415

    db_path = str(tmp_path / "centralino_test.db")
    repo = CallLogRepository(db_path=db_path)
    await repo.init_db()

    # Seed a minimal tenant row so the FK on call_logs.tenant_id is satisfied
    import aiosqlite  # noqa: PLC0415
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR REPLACE INTO tenants
               (id, business_name, greeting, voice_id, system_prompt)
               VALUES (?, ?, ?, ?, ?)""",
            ("demo", "Ristorante Test", "Ciao", "voice-abc", "Sei un assistente."),
        )
        await db.commit()

    return repo


# ---------------------------------------------------------------------------
# Task 2 tests — RED until repository.py is implemented
# ---------------------------------------------------------------------------

async def test_write_row_roundtrip(call_log_repo, tmp_path):
    """NOTIF-01: written row is selectable with the stored outcome and transcript.

    Inserts one call_logs row via CallLogRepository.write() and reads it back
    directly via aiosqlite to confirm the outcome, transcript_json, and
    tenant_id are stored correctly.
    """
    import aiosqlite  # noqa: PLC0415

    transcript = [
        {"role": "assistant", "content": "Ciao, posso aiutarla?"},
        {"role": "user", "content": "Vorrei prenotare un tavolo."},
    ]

    rowid = await call_log_repo.write(
        tenant_id="demo",
        started_at="2026-06-27T12:00:00+02:00",
        outcome="faq",
        transcript_json=transcript,
        summary_text="Il cliente ha chiesto informazioni sugli orari.",
    )

    assert isinstance(rowid, int), "write() must return an integer rowid"
    assert rowid > 0, "rowid must be a positive integer"

    # Read back directly to confirm storage
    db_path = call_log_repo._db_path
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM call_logs WHERE id = ?", (rowid,)
        ) as cur:
            row = await cur.fetchone()

    assert row is not None, "Written row must be fetchable by rowid"
    assert row["tenant_id"] == "demo"
    assert row["outcome"] == "faq"
    assert row["summary_text"] == "Il cliente ha chiesto informazioni sugli orari."

    # transcript_json round-trips as a JSON array
    loaded = json.loads(row["transcript_json"])
    assert loaded == transcript, "transcript_json must round-trip as a JSON array"


async def test_outcome_check_constraint(call_log_repo):
    """D-06: outcome values outside the five-value taxonomy raise IntegrityError.

    The CHECK constraint on call_logs.outcome must reject any value not in
    {prenotato, faq, trasferito, abbandonato, fallito}.
    """
    with pytest.raises(Exception) as exc_info:
        await call_log_repo.write(
            tenant_id="demo",
            started_at="2026-06-27T12:00:00+02:00",
            outcome="INVALID_OUTCOME",  # not in the five-value taxonomy
            transcript_json=[{"role": "user", "content": "test"}],
        )

    # WR-07: assert the exact type — the old `(sqlite3.IntegrityError, Exception)`
    # tuple was a tautology (everything subclasses Exception), so the test passed
    # even for unrelated errors. CHECK violations raise sqlite3.IntegrityError.
    assert exc_info.type is sqlite3.IntegrityError, (
        f"Invalid outcome must raise sqlite3.IntegrityError, got: {exc_info.type!r}"
    )
    # The error must reference the constraint (not a silent insert of wrong data)
    err_str = str(exc_info.value).lower()
    assert any(kw in err_str for kw in ("constraint", "check", "integrity", "fail")), (
        f"Exception must indicate a constraint violation, got: {exc_info.value!r}"
    )


async def test_transcript_json_stores_array(call_log_repo):
    """transcript_json persists a list of message dicts correctly.

    Ensures ensure_ascii=False is used (Italian characters survive round-trip).
    """
    transcript = [
        {"role": "assistant", "content": "Buongiorno! Come posso aiutarla?"},
        {"role": "user", "content": "Cerco un tavolo per stasera. È possibile?"},
    ]

    rowid = await call_log_repo.write(
        tenant_id="demo",
        started_at="2026-06-27T12:05:00+02:00",
        outcome="prenotato",
        transcript_json=transcript,
    )

    import aiosqlite  # noqa: PLC0415
    db_path = call_log_repo._db_path
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT transcript_json FROM call_logs WHERE id = ?", (rowid,)
        ) as cur:
            row = await cur.fetchone()

    assert row is not None
    # WR-07: exercise the ensure_ascii=False guarantee directly. The old assertion's
    # right operand (content ends in "?") was always true, so the accented-char check
    # was never reached. The fixture contains "È" (U+00C8); assert it is stored
    # literally and NOT as its \uXXXX escape.
    raw = row[0]
    assert "È" in raw, (
        "Italian accented characters must be stored literally (ensure_ascii=False)"
    )
    assert "\\u00c8" not in raw, (
        "Accented characters must NOT be \\uXXXX-escaped (ensure_ascii=False)"
    )
    assert json.loads(raw) == transcript


# ---------------------------------------------------------------------------
# _determine_outcome tests — RED until summary.py is implemented
# ---------------------------------------------------------------------------

def test_determine_outcome_explicit_override():
    """Explicit state['outcome'] wins over all other logic."""
    from src.call_log.summary import _determine_outcome  # noqa: PLC0415

    state = {"outcome": "trasferito", "confirmed_event_id": "evt-123"}
    assert _determine_outcome(state) == "trasferito"


def test_determine_outcome_confirmed_event():
    """confirmed_event_id (no explicit outcome) → 'prenotato'."""
    from src.call_log.summary import _determine_outcome  # noqa: PLC0415

    state = {"confirmed_event_id": "evt-123"}
    assert _determine_outcome(state) == "prenotato"


def test_determine_outcome_faq_answered():
    """faq_answered flag (no booking) → 'faq'."""
    from src.call_log.summary import _determine_outcome  # noqa: PLC0415

    state = {"faq_answered": True}
    assert _determine_outcome(state) == "faq"


def test_determine_outcome_booking_slot_no_event():
    """booking_slot set but confirmed_event_id absent → 'abbandonato'."""
    from src.call_log.summary import _determine_outcome  # noqa: PLC0415

    state = {"booking_slot": {"date": "2026-07-10", "time": "20:00"}}
    assert _determine_outcome(state) == "abbandonato"


def test_determine_outcome_empty_state():
    """Empty state → 'faq' (default — no booking attempted)."""
    from src.call_log.summary import _determine_outcome  # noqa: PLC0415

    assert _determine_outcome({}) == "faq"


def test_determine_outcome_trasferito_from_01():
    """outcome='trasferito' set by 03-01 transfer handler is respected (prior context)."""
    from src.call_log.summary import _determine_outcome  # noqa: PLC0415

    # flow state as left by 03-01's handle_transfer_call
    state = {
        "outcome": "trasferito",
        "transfer_payload": {"transfer_number": "+39 02 1234567", "reason": "richiesta_cliente"},
        "transfer_reason": "richiesta_cliente",
    }
    assert _determine_outcome(state) == "trasferito"
