"""LocalTransferStub — in-process TelephonyProvider for local/dev path (D-01, Phase 3).

No real telephony API is called.  The stub logs the transfer intent only and
returns cleanly.

Frame side-effects (TTSSpeakFrame courtesy phrase + EndWorkerFrame for clean
shutdown) are the responsibility of ``handle_transfer_call`` in
``src/flows/functions.py`` — NOT of this stub.  The stub is the domain seam;
the handler owns the pipeline-level effects.

Security (T-03-LOG): only ``number`` (the operator's configured line) and
``context.get('reason')`` are logged.  Caller name, phone, or any full transcript
are NEVER logged here.
"""

from __future__ import annotations

from loguru import logger

from src.telephony.base import TelephonyProvider


class LocalTransferStub(TelephonyProvider):
    """Local/dev TelephonyProvider — logs intent, no real API call (D-01).

    Phase 4 replaces this with a ``TelnyxTelephonyProvider`` (or similar)
    behind the same ``TelephonyProvider`` interface without changing any
    conversational logic.
    """

    async def transfer(self, number: str, context: dict) -> None:
        """Log the transfer intent and return.

        Security (T-03-LOG):
        - Only ``number`` (operator's configured line) and ``reason`` are logged.
        - Caller PII (name, phone, transcript) is intentionally NEVER logged.
        """
        reason = context.get("reason", "richiesta_cliente")
        logger.info(
            f"[TRANSFER STUB] Initiating local transfer → {number!r} "
            f"(reason: {reason!r})"
        )
        # Phase 4: real implementation places a SIP REFER / Dial+Bridge here.
        # Local path: log-and-return; pipeline shutdown is handled by the caller
        # (handle_transfer_call queues EndWorkerFrame upstream).
