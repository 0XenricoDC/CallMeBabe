"""NotificationChannelFactory — per-tenant channel selection (NOTIF-05, D-11).

Maps the tenant's ``notification_channel`` config value to a concrete
``NotificationChannel`` instance, reading all credentials exclusively from
environment variables (T-03-NINJ).

Mirrors ``get_stt_provider`` in ``src/pipeline/factory.py``:
- A name → class dict with an explicit fallback.
- Credentials sourced only via ``os.getenv`` — never from caller args or tenant config.
- Unknown / None names fall back to the demo-default branch (D-11).

Demo-default multi-send (D-11):
  When the channel name is unset / None / "log" AND both TELEGRAM_BOT_TOKEN and
  TELEGRAM_CHAT_ID are present (non-empty) in the environment, the factory returns
  MultiNotificationChannel([LogNotificationChannel(), TelegramNotificationChannel(...)])
  so the end-of-call summary is dispatched to BOTH the console log AND Telegram.
  When either Telegram env var is absent or empty, it returns LogNotificationChannel()
  only — no crash, no partial Telegram send.

Security:
- T-03-NINJ: channel targets (chat_id, SMTP_TO, token) come only from env via this
  factory. The ``tenant`` arg selects the channel *name* only — zero routing influence
  from caller args or the transcript.  Both Telegram env vars must be non-empty before
  the Telegram leg is added to the composite.
- T-03-TOK: tokens/passwords stored in .env (gitignored), shown as placeholders in
  .env.example; never hardcoded or logged.
"""

from __future__ import annotations

import os

from src.interfaces.notification_channel import NotificationChannel
from src.notifications.email_channel import EmailNotificationChannel
from src.notifications.log_channel import LogNotificationChannel
from src.notifications.multi_channel import MultiNotificationChannel
from src.notifications.sms_channel import SMSNotificationChannel
from src.notifications.telegram_channel import TelegramNotificationChannel


def create_channel(name: str | None, tenant) -> NotificationChannel:
    """Return the ``NotificationChannel`` instance for the given channel name.

    Channel name is taken from ``tenant.notification_channel`` (or the explicit
    ``name`` arg). All credentials are read via ``os.getenv`` inside this factory —
    the returned channel object never calls ``os.getenv`` itself.

    Args:
        name:   Channel name string: ``"log"``, ``"telegram"``, ``"email"``,
                ``"sms"``, ``"whatsapp"``, or ``None``.
                ``None`` / ``"log"`` / unknown → demo-default branch (D-11):
                multi-send if Telegram env vars present; log-only otherwise.
        tenant: TenantConfig instance (used for future per-tenant credential
                overrides; currently only ``name`` is used for dispatch).

    Returns:
        A concrete ``NotificationChannel`` ready for ``await channel.send(...)``.
    """
    normalized = (name or "").strip().lower()

    if normalized == "telegram":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        return TelegramNotificationChannel(token=token, chat_id=chat_id)

    if normalized == "email":
        return EmailNotificationChannel(
            host=os.getenv("SMTP_HOST", ""),
            port=int(os.getenv("SMTP_PORT", "587")),
            user=os.getenv("SMTP_USER", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            to=os.getenv("SMTP_TO", ""),
            from_=os.getenv("SMTP_FROM", ""),
        )

    if normalized in ("sms", "whatsapp"):
        return SMSNotificationChannel()

    # Demo-default branch: "log" / unknown / None (D-11 multi-send)
    # Both Telegram env vars must be present (non-empty) for the telegram leg to be added.
    # T-03-NINJ: destinations come ONLY from env — never from caller or transcript.
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        return MultiNotificationChannel(
            [
                LogNotificationChannel(),
                TelegramNotificationChannel(token=token, chat_id=chat_id),
            ]
        )

    # Fallback: no Telegram vars → log only
    return LogNotificationChannel()
