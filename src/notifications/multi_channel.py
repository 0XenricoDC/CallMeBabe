"""MultiNotificationChannel — composite channel for demo-default multi-send (D-11).

Purpose (D-11): When the demo tenant's notification_channel is unset/None/log AND
both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are present in the environment, the
end-of-call summary is dispatched via BOTH the log channel AND Telegram.
create_channel() in factory.py builds and returns this composite for that case.

Security posture:
- T-03-NINJ: Channel destinations (token, chat_id) are resolved ONLY via os.getenv
  inside the factory before constructing the wrapped channels. This composite never
  reads os.getenv itself — the factory is the sole env-reading boundary.
- T-03-LOGPII: On per-channel failure, only type(exc).__name__ is logged. The
  notification subject and body (which may name the caller) are never logged.
- T-03-FIN: Per-channel try/except ensures one channel failure never propagates to
  the caller or blocks remaining channels. Call shutdown is never interrupted.
"""

from __future__ import annotations

from loguru import logger

from src.interfaces.notification_channel import NotificationChannel


class MultiNotificationChannel(NotificationChannel):
    """Composite notification channel: dispatches to every wrapped channel in order.

    Failure isolation: if one channel's send() raises, the exception is caught,
    logged by exception type only (T-03-LOGPII), and the remaining channels are
    still invoked. The send() method itself never raises.

    Args:
        channels: Ordered list of NotificationChannel instances to dispatch to.
                  Exposed as the ``channels`` attribute for introspection/tests.
    """

    def __init__(self, channels: list[NotificationChannel]) -> None:
        self.channels = channels

    async def send(self, subject: str, body: str) -> None:
        """Deliver subject + body to every wrapped channel with per-channel isolation.

        Args:
            subject: Notification subject (e.g. "Chiamata 29/06 14:30 — Prenotato").
            body:    2-3 sentence Italian call summary (not the full transcript).
        """
        for channel in self.channels:
            try:
                await channel.send(subject, body)
            except Exception as exc:  # noqa: BLE001
                # Security (T-03-LOGPII): NEVER log subject/body — they may contain PII.
                # Only the exception type and the failing channel class are logged.
                logger.error(
                    f"MultiNotificationChannel: {type(exc).__name__} "
                    f"in {type(channel).__name__} — continuing to next channel"
                )
