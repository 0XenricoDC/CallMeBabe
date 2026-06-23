"""Wave 0 stub for the greeting-on-connect behaviour (VOICE-02).

RED stub: the bot module does not exist yet (built in Plan 02). xfail-marked so
the suite stays green-on-xfail; Plan 02 removes the marker.
"""

import pytest

PLAN_02 = "implemented in Plan 02 (bot speaks first / greeting injection)"


@pytest.mark.xfail(reason=PLAN_02, strict=False)
def test_greeting_injected(tenant):
    """VOICE-02 / D-11: on client connect the bot queues the tenant greeting.

    TODO(Plan 02): the on_client_connected handler must queue a TTSSpeakFrame whose
    text == tenant.greeting (barge-in active during the greeting itself).
    """
    from src.bot import on_client_connected  # noqa: F401  (created in Plan 02)

    raise AssertionError("greeting injection not implemented yet (Plan 02)")
