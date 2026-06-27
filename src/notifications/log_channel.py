"""LogNotificationChannel — zero-dependency default notification channel (D-10, D-11).

Writes the end-of-call subject + summary to loguru. Used as the default fallback
for demo tenants and any tenant whose notification_channel is not configured.
No external API calls, no credentials required.

Security:
- T-03-LOGPII: exception handlers never log subject/body (potential PII).
- T-03-TOK: no tokens or secrets needed.
"""

from __future__ import annotations

from loguru import logger

from src.interfaces.notification_channel import NotificationChannel


class LogNotificationChannel(NotificationChannel):
    """Write the call summary to the loguru console log (D-10 REAL default).

    This is the zero-dependency channel that works out of the box for local
    development and is the automatic fallback when no other channel is configured
    (D-11). All tenants whose ``notification_channel`` field is ``None`` or ``"log"``
    use this implementation.
    """

    async def send(self, subject: str, body: str) -> None:
        """Log the notification to the console via loguru.

        Args:
            subject: Notification subject (e.g. "Chiamata 27/06 14:30 — Prenotato").
            body:    2-3 sentence Italian call summary (NOT the full transcript).
        """
        try:
            logger.info(f"[CALL LOG] {subject}\n{body}")
        except Exception as exc:  # noqa: BLE001
            # Security (T-03-LOGPII): NEVER log subject/body (may contain PII).
            logger.error(f"LogNotificationChannel.send failed: {type(exc).__name__}")
