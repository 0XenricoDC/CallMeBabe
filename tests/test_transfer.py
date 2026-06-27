"""Tests for the global transfer function and TelephonyProvider seam (HAND-01/03/04).

RED state (Task 1): tests import from src.flows.functions which does NOT yet
expose build_transfer_schema / handle_transfer_call — they will FAIL/ERROR until
Task 2 implements those.  That is the expected RED state per TDD protocol.

Coverage:
- test_transfer_uses_config_number_not_args   (T-03-INJ — malicious args ignored)
- test_transfer_sets_outcome_trasferito        (D-06 outcome taxonomy)
- test_global_function_visible                 (HAND-04 — schema named transfer_call)
- test_non_italian_reason_supported            (HAND-03 — reason forwarded safely)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs — mirror test_observers.py pattern
# ---------------------------------------------------------------------------

@dataclass
class _FakeProcessor:
    """Minimal FrameProcessor stand-in whose .name is a plain string."""
    name: str


@dataclass
class _FakeFramePushed:
    """FramePushed stand-in."""
    source: _FakeProcessor
    frame: object
    destination: object = None
    direction: object = None
    timestamp: int = 0


class _SpyWorker:
    """Records all frames queued via queue_frames / queue_frame."""

    def __init__(self):
        self.queued: list = []

    async def queue_frames(self, frames):
        self.queued.extend(frames)

    async def queue_frame(self, frame, direction=None):
        self.queued.append(frame)


class _FakeTenant:
    """Minimal TenantConfig stand-in."""

    def __init__(self, transfer_number: str | None = "+39 02 1234567"):
        self.transfer_number = transfer_number
        self.business_name = "Ristorante Test"
        self.id = "demo"


class _FakeFlowManager:
    """Minimal FlowManager stand-in with .state dict and ._worker spy."""

    def __init__(self, tenant=None):
        self.state: dict = {
            "tenant": tenant or _FakeTenant(),
            "tenant_id": "demo",
            "booking_slot": None,
            "customer": None,
            "confirmed_event_id": None,
        }
        self.worker = _SpyWorker()


# ---------------------------------------------------------------------------
# Task 1 tests — these FAIL (RED) until Task 2 implements the schema/handler
# ---------------------------------------------------------------------------

def test_global_function_visible():
    """HAND-04: build_transfer_schema() returns a FlowsFunctionSchema named 'transfer_call'.

    Tests that the schema builder exists and returns the right name.
    This test is in RED state until Task 2 adds build_transfer_schema().
    """
    from src.flows.functions import build_transfer_schema  # noqa: PLC0415

    schema = build_transfer_schema()
    assert schema.name == "transfer_call", (
        f"Expected schema name 'transfer_call', got {schema.name!r}"
    )


async def test_transfer_uses_config_number_not_args():
    """T-03-INJ: handler ignores transfer_number in args; reads ONLY from tenant config.

    A malicious caller could try to set args['transfer_number'] = '+1-555-ATTACKER'.
    The handler MUST resolve the number exclusively from fm.state['tenant'].transfer_number.
    """
    from src.flows.functions import handle_transfer_call  # noqa: PLC0415

    tenant = _FakeTenant(transfer_number="+39 02 1234567")
    fm = _FakeFlowManager(tenant=tenant)

    # Attacker tries to supply their own transfer_number in args
    malicious_args = {
        "reason": "richiesta_cliente",
        "transfer_number": "+1-555-ATTACKER",  # must be IGNORED
    }

    await handle_transfer_call(malicious_args, fm)

    # The transfer payload must use the tenant's configured number, never the arg
    payload = fm.state.get("transfer_payload", {})
    assert payload.get("transfer_number") == "+39 02 1234567", (
        f"Handler must use tenant config number, not args. Got: {payload.get('transfer_number')!r}"
    )
    assert payload.get("transfer_number") != "+1-555-ATTACKER", (
        "Handler must NOT use the malicious transfer_number from args."
    )


async def test_transfer_sets_outcome_trasferito():
    """D-06: handle_transfer_call sets fm.state['outcome'] to 'trasferito'."""
    from src.flows.functions import handle_transfer_call  # noqa: PLC0415

    fm = _FakeFlowManager()
    await handle_transfer_call({"reason": "richiesta_cliente"}, fm)

    assert fm.state.get("outcome") == "trasferito", (
        f"Expected outcome='trasferito', got: {fm.state.get('outcome')!r}"
    )


async def test_non_italian_reason_supported():
    """HAND-03: handle_transfer_call accepts any reason string (non-Italian too).

    The 'reason' arg is safe (logged only, never used for routing).
    A non-Italian reason like 'lingua_non_supportata' must not cause errors.
    """
    from src.flows.functions import handle_transfer_call  # noqa: PLC0415

    fm = _FakeFlowManager()
    result, next_node = await handle_transfer_call(
        {"reason": "lingua_non_supportata"}, fm
    )

    # Handler must succeed regardless of reason value
    assert result is not None, "Handler must return a result dict"
    # outcome must still be set
    assert fm.state.get("outcome") == "trasferito"
    # transfer_payload must carry the reason for the warm payload (D-04)
    payload = fm.state.get("transfer_payload", {})
    assert payload.get("reason") == "lingua_non_supportata", (
        f"Warm payload must include the reason. Got: {payload.get('reason')!r}"
    )


# ---------------------------------------------------------------------------
# Stub tests — these PASS immediately (stub is implemented in Task 1)
# ---------------------------------------------------------------------------

async def test_local_transfer_stub_no_pii_in_log(caplog):
    """T-03-LOG: LocalTransferStub must not log caller PII (name/phone).

    Injects a context dict with caller PII and asserts PII does not appear
    in any log record emitted by the stub.
    """
    import logging  # noqa: PLC0415

    from src.telephony.stub import LocalTransferStub  # noqa: PLC0415

    stub = LocalTransferStub()

    pii_context = {
        "reason": "richiesta_cliente",
        "customer": {"name": "Mario Rossi", "phone": "333 1234567"},
        "booking_slot": {"date": "2026-07-10", "time_slot": "20:00"},
    }

    # Capture loguru output via propagation to stdlib root logger
    import loguru  # noqa: PLC0415

    captured_messages: list[str] = []

    def _sink(message):
        captured_messages.append(str(message))

    handler_id = loguru.logger.add(_sink, level="DEBUG")
    try:
        await stub.transfer(number="+39 02 111222", context=pii_context)
    finally:
        loguru.logger.remove(handler_id)

    # PII must not appear in any captured log message
    full_log = " ".join(captured_messages)
    assert "Mario Rossi" not in full_log, "Caller name must NOT be logged by stub"
    assert "333 1234567" not in full_log, "Caller phone must NOT be logged by stub"
    # WR-07: assert unconditionally that the caller's phone digits are absent. The
    # old `... or "transfer" in full_log.lower()` could never fail because the stub
    # always logs the word "transfer", so the PII check was inert.
    assert "333" not in full_log, (
        "Caller phone digits must not leak into stub log output"
    )
