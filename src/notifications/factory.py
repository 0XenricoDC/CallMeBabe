"""NotificationChannelFactory — per-tenant channel selection (NOTIF-05, D-11).

Maps the tenant's ``notification_channel`` config value to a concrete
``NotificationChannel`` instance, reading all credentials exclusively from
environment variables (T-03-NINJ).

Mirrors ``get_stt_provider`` in ``src/pipeline/factory.py``:
- A name → class dict with an explicit fallback.
- Credentials sourced only via ``os.getenv`` — never from caller args or tenant config.
- Unknown / None names fall back to ``LogNotificationChannel`` (D-11 default).

Security:
- T-03-NINJ: channel targets (chat_id, SMTP_TO, token) come only from env via this
  factory. The ``tenant`` arg selects the channel *name* only — zero routing influence
  from caller args or the transcript.
- T-03-TOK: tokens/passwords stored in .env (gitignored), shown as placeholders in
  .env.example; never hardcoded or logged.
"""

from __future__ import annotations

import os

from src.interfaces.notification_channel import NotificationChannel
from src.notifications.email_channel import EmailNotificationChannel
from src.notifications.log_channel import LogNotificationChannel
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
                ``None`` or any unknown value falls back to ``LogNotificationChannel``
                (D-11 default).
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

    # Default / fallback: "log" or any unknown/None name → LogNotificationChannel (D-11)
    return LogNotificationChannel()
