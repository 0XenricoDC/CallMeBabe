"""SMSNotificationChannel — Phase 3 stub for SMS/WhatsApp (D-10).

A minimal stub that logs the intent without calling any external SMS/WhatsApp API.
The real implementation (Telnyx Messaging or Twilio) is deferred to Phase 4+.

Security:
- T-03-NINJ: no external routing possible; stub intentionally calls no API.
- T-03-LOGPII: logs only the [SMS STUB] marker — never the subject or body.
"""

from __future__ import annotations

from loguru import logger

from src.interfaces.notification_channel import NotificationChannel


class SMSNotificationChannel(NotificationChannel):
    """Phase 3 stub for SMS/WhatsApp notification dispatch (D-10).

    Logs a ``[SMS STUB]`` line so the operator can see the channel was invoked
    during testing. Makes NO external API call — the real provider (Telnyx Messaging
    or Twilio) is wired in Phase 4+.

    This class also serves the ``whatsapp`` channel name (same stub, same interface).
    """

    async def send(self, subject: str, body: str) -> None:
        """Log that an SMS/WhatsApp notification would be sent (Phase 3 stub).

        Args:
            subject: Notification subject (logged at DEBUG for traceability).
            body:    Call summary (NOT logged — potential PII).
        """
        try:
            # Security (T-03-LOGPII): do NOT log body (caller PII). Subject is
            # logged at DEBUG level only to aid development tracing.
            logger.debug(f"[SMS STUB] would send: {subject}")
        except Exception as exc:  # noqa: BLE001
            # Security (T-03-LOGPII): NEVER log subject/body in except handler.
            logger.error(f"SMSNotificationChannel.send failed: {type(exc).__name__}")
