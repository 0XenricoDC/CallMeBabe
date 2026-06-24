"""Error fallback observer — Italian courtesy phrase on provider error (REL-01).

On a non-fatal ErrorFrame from any service (STT/LLM/TTS), the observer queues a
`TTSSpeakFrame` with the generic Italian courtesy phrase so the user hears a spoken
prompt instead of dead-air (REL-01, D-07).

D-07: one fast retry slot per error source before speaking the courtesy phrase.
On the first non-fatal ErrorFrame from a given source, the retry slot is consumed
(service-level auto-retry is expected to handle the actual retry); on the second
occurrence the courtesy phrase is queued and the counter resets.

Security (V7 / T-03-LOG):
  - The raw ErrorFrame.error string is NEVER printed or logged.
  - The sanitized `source.name` (service class name, no key) is all that is used.
  - No os.getenv("*_API_KEY") values are referenced or logged here.
"""

from __future__ import annotations

from pipecat.frames.frames import ErrorFrame, TTSSpeakFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed

# D-07: single generic Italian courtesy phrase — no per-stage phrase variants.
COURTESY_PHRASE: str = "Mi scusi, ho avuto un problema tecnico, può ripetere?"


class ErrorFallbackObserver(BaseObserver):
    """Intercept non-fatal ErrorFrames and queue an Italian courtesy phrase.

    D-07 retry logic (per source):
      - First ErrorFrame from a source: retry slot consumed (service-level retry assumed).
      - Second ErrorFrame from the same source: courtesy phrase queued; counter resets.

    The worker reference is set via __init__ and may be updated after worker creation
    (see bot.py wiring) to break the circular construction dependency.

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
        # Tracks retry-slot consumption per source name.
        self._retry_counts: dict[str, int] = {}

    async def on_push_frame(self, data: FramePushed) -> None:
        """Act only on non-fatal ErrorFrames; queue courtesy phrase after retry slot."""
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
