"""TelephonyProvider interface seam (Phase 3 — operator handoff).

Defined now so the handoff phase adds a concrete implementation (e.g. Telnyx SIP)
*behind* this interface rather than restructuring conversational logic.

Security (T-injection, T-03-INJ): the `number` parameter MUST always be resolved
from the trusted tenant configuration (``fm.state["tenant"].transfer_number``);
it must NEVER be derived from caller-supplied tool arguments.  Callers supply only
a human-readable ``reason`` string for logging — the routing target is always the
tenant-configured operator number, not anything the caller can influence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class TelephonyProvider(ABC):
    """Telephony backend for operator transfer (Phase 3 seam).

    The `number` argument to `transfer()` MUST come exclusively from trusted
    tenant configuration — callers never supply a raw transfer target.
    Phase 4 replaces the local stub with a real SIP/Dial implementation without
    touching any conversational logic.
    """

    @abstractmethod
    async def transfer(self, number: str, context: dict) -> None:
        """Initiate a transfer to the operator's configured number.

        Args:
            number: The operator's phone number, resolved from
                    ``TenantConfig.transfer_number`` (trusted config only —
                    NEVER from caller-supplied args; T-injection prevention).
            context: A warm-ready payload dict (D-04) containing
                     ``reason``, ``booking_slot``, ``customer``, and
                     ``confirmed_event_id``.  Phase 4 uses this for a real
                     warm-transfer briefing; Phase 3 logs it only.
        """
        raise NotImplementedError
