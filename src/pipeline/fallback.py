"""Error fallback observer — Italian courtesy phrase on provider error (REL-01/REL-02).

On a non-fatal ErrorFrame from any service (STT/LLM/TTS), the observer queues a
`TTSSpeakFrame` with the generic Italian courtesy phrase so the user hears a spoken
prompt instead of dead-air (REL-01, D-07).

D-07: one fast retry slot per error source before speaking the courtesy phrase.
On the first non-fatal ErrorFrame from a given source, the retry slot is consumed
(service-level auto-retry is expected to handle the actual retry); on the second
occurrence the courtesy phrase is queued and the counter resets.

REL-02 / D-13: escalation after _ESCALATION_THRESHOLD retry-slot cycles.
After N exhausted retry slots from the same source (meaning N×2 ErrorFrames have
been seen), the observer escalates: sets outcome='fallito', queues a transfer
courtesy phrase and EndWorkerFrame. Fires exactly once (_escalated idempotency guard).

Security (V7 / T-03-LOG):
  - The raw ErrorFrame.error string is NEVER printed or logged.
  - The sanitized `source.name` (service class name, no key) is all that is used.
  - No os.getenv("*_API_KEY") values are referenced or logged here.
  - Courtesy and escalation phrases are static strings — no ErrorFrame content.
"""

from __future__ import annotations

from pipecat.frames.frames import EndWorkerFrame, ErrorFrame, TTSSpeakFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed

# D-07: single generic Italian courtesy phrase — no per-stage phrase variants.
COURTESY_PHRASE: str = "Mi scusi, ho avuto un problema tecnico, può ripetere?"

# REL-02 / D-13: escalation threshold.
# After this many retry-slot cycles (each cycle = retry slot exhausted → courtesy phrase)
# from a single source, the observer escalates to transfer + EndWorkerFrame.
# Claude's Discretion: 3 cycles = 6 ErrorFrames before giving up — generous for transient
# errors, decisive enough to avoid prolonged dead-air if a service is truly down (SC4).
_ESCALATION_THRESHOLD: int = 3

# REL-02: static escalation transfer phrase — no PII, no ErrorFrame content (V7/T-03-LOG).
_ESCALATION_PHRASE: str = (
    "Mi scusi, sto riscontrando problemi tecnici. La trasferisco a un operatore."
)


class ErrorFallbackObserver(BaseObserver):
    """Intercept non-fatal ErrorFrames and queue an Italian courtesy phrase.

    D-07 retry logic (per source):
      - First ErrorFrame from a source: retry slot consumed (service-level retry assumed).
      - Second ErrorFrame from the same source: courtesy phrase queued; counter resets.

    REL-02 escalation logic (per source, after D-07 retry):
      - Each time the retry slot is exhausted for a source, an escalation counter
        is incremented.
      - When the escalation counter reaches _ESCALATION_THRESHOLD AND _escalated is False,
        the observer sets flow_manager.state['outcome']='fallito', queues the escalation
        phrase + EndWorkerFrame, and sets _escalated=True (idempotent guard).

    The worker reference is set via __init__ and may be updated after worker creation
    (see bot.py wiring) to break the circular construction dependency.

    The flow_manager reference defaults to None and must be set after FlowManager
    creation in bot.py:  ``error_observer.flow_manager = flow_manager``

    Security (V7): ErrorFrame.error and ErrorFrame.exception are never printed/logged.
    Only the sanitized source name (service class name, no secret values) is used.
    """

    def __init__(self, worker) -> None:
        """Create the observer.

        Args:
            worker: The `PipelineWorker` that owns the pipeline. Used to queue the
                    courtesy `TTSSpeakFrame`. May be set after construction if there
                    is a circular dependency — assign to `observer.worker` before use.
        """
        super().__init__()
        self.worker = worker
        # REL-02: FlowManager ref — set by bot.py after FlowManager creation.
        # None until patched; guards in on_push_frame check before use.
        self.flow_manager = None
        # Tracks retry-slot consumption per source name (D-07).
        self._retry_counts: dict[str, int] = {}
        # Tracks escalation cycles per source name (REL-02).
        self._escalation_counts: dict[str, int] = {}
        # Idempotency guard: escalation fires exactly once per call (REL-02).
        self._escalated: bool = False

    async def on_push_frame(self, data: FramePushed) -> None:
        """Act only on non-fatal ErrorFrames; queue courtesy phrase after retry slot.

        After _ESCALATION_THRESHOLD retry-slot cycles, escalates to transfer.
        """
        frame = data.frame

        if not isinstance(frame, ErrorFrame):
            return

        # Fatal errors are unrecoverable — do not queue courtesy phrase, let the
        # pipeline shut down normally (the runner will close the session).
        if frame.fatal:
            return

        # Sanitized source name only — never log the error string (V7 / T-03-LOG).
        src_name: str = getattr(data.source, "name", "unknown-service") or "unknown-service"

        count = self._retry_counts.get(src_name, 0)
        if count < 1:
            # D-07: first occurrence → consume retry slot.
            # Service-level retry is expected to handle re-sending the request;
            # we do not trigger a manual retry here because we cannot safely
            # replay arbitrary frames from an observer.
            self._retry_counts[src_name] = count + 1
        else:
            # D-07: retry slot exhausted → speak courtesy phrase instead of dead-air.
            self._retry_counts[src_name] = 0
            await self.worker.queue_frames(
                [TTSSpeakFrame(text=COURTESY_PHRASE, append_to_context=False)]
            )

            # REL-02: track how many times the retry slot has been exhausted for this source.
            esc_count = self._escalation_counts.get(src_name, 0) + 1
            self._escalation_counts[src_name] = esc_count

            # REL-02 escalation: after N consecutive courtesy-phrase cycles, give up.
            # _escalated guard ensures this fires at most once per call session (SC4).
            if esc_count >= _ESCALATION_THRESHOLD and not self._escalated:
                self._escalated = True
                # Record 'fallito' outcome for the end-of-call hook (D-06 taxonomy).
                if self.flow_manager is not None:
                    self.flow_manager.state["outcome"] = "fallito"
                # Queue: escalation phrase + EndWorkerFrame (SC4 — no long dead-air).
                # EndWorkerFrame terminates the pipeline cleanly (same pattern as
                # handle_transfer_call in flows/functions.py).
                # Security (V7/T-03-LOG): phrase is static — no ErrorFrame.error content.
                await self.worker.queue_frames([
                    TTSSpeakFrame(
                        text=_ESCALATION_PHRASE,
                        append_to_context=False,
                    ),
                    EndWorkerFrame(),
                ])
