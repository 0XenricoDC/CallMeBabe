"""EmailNotificationChannel — SMTP email channel via aiosmtplib (D-10, code-complete).

Sends the end-of-call summary as a plain-text email using STARTTLS SMTP.
Code is fully implemented and tested with mocked SMTP in unit tests; live testing
requires valid SMTP_* credentials in .env (added in Phase 3, D-10).

Security:
- T-03-NINJ: all SMTP credentials (host/port/user/password/to/from) come only
  from env vars resolved by the factory. Zero influence from caller input.
- T-03-LOGPII: on send failure, only the exception type is logged — never the
  email body or subject (may contain PII).
- T-03-TOK: SMTP_PASSWORD never hardcoded or logged.
"""

from __future__ import annotations

import email.message

from loguru import logger

from src.interfaces.notification_channel import NotificationChannel


class EmailNotificationChannel(NotificationChannel):
    """Send the call summary via SMTP (STARTTLS) using aiosmtplib (D-10 REAL).

    Credentials must come from environment variables, resolved by the factory and
    passed as constructor arguments. The channel never reads ``os.getenv`` itself.

    Args:
        host:     SMTP server hostname (e.g. "smtp.gmail.com").
        port:     SMTP port, typically 587 for STARTTLS.
        user:     SMTP account username.
        password: SMTP account password or app-specific password.
        to:       Recipient email address (owner notification target).
        from_:    Sender email address.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        to: str,
        from_: str,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._to = to
        self._from = from_

    async def send(self, subject: str, body: str) -> None:
        """Send an email notification with the call summary.

        Args:
            subject: Email subject line (e.g. "Chiamata 27/06 14:30 — Prenotato").
            body:    2-3 sentence Italian call summary (NOT the full transcript).
        """
        import aiosmtplib  # noqa: PLC0415

        msg = email.message.EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = self._to
        msg.set_content(body)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._host,
                port=self._port,
                username=self._user,
                password=self._password,
                start_tls=True,
            )
        except Exception as exc:  # noqa: BLE001
            # Security (T-03-LOGPII): NEVER log subject/body (may contain caller PII).
            logger.error(
                f"EmailNotificationChannel.send failed: {type(exc).__name__}"
            )
