"""Wave 0 stubs for the observers (VOICE-04 metrics, REL-01 error fallback).

RED stubs: the observers module does not exist yet (built in Plan 03). xfail-marked
so the suite stays green-on-xfail; Plan 03 removes the markers.
"""

import pytest

PLAN_03 = "implemented in Plan 03 (latency + error-fallback observers)"


@pytest.mark.xfail(reason=PLAN_03, strict=False)
def test_latency_observer():
    """VOICE-04 / D-06: LatencyObserver emits a per-turn human-readable line + JSONL.

    TODO(Plan 03): feed MetricsFrames and assert the console line of the form
    `turn=...ms | stt=... llm_ttft=... tts_ttfb=...` and a JSONL record are produced.
    """
    from src.pipeline.observers import LatencyObserver  # noqa: F401  (created in Plan 03)

    raise AssertionError("LatencyObserver not implemented yet (Plan 03)")


@pytest.mark.xfail(reason=PLAN_03, strict=False)
def test_error_fallback():
    """REL-01 / D-07: a non-fatal ErrorFrame triggers an Italian courtesy phrase.

    TODO(Plan 03): a non-fatal ErrorFrame (after the single retry) injects a
    TTSSpeakFrame with the courtesy phrase instead of dead-air.
    """
    from src.pipeline.observers import ErrorFallbackObserver  # noqa: F401  (created in Plan 03)

    raise AssertionError("ErrorFallbackObserver not implemented yet (Plan 03)")
