"""Tests for notification channels + factory (NOTIF-03, NOTIF-04, NOTIF-05).

Coverage:
- test_channels: all four channel classes instantiate and expose async send().
  Telegram and email calls are patched so no network is required.
- test_factory: create_channel() returns the correct concrete class for each
  channel name, including the unknown/None fallback to LogNotificationChannel.

TDD note: test_factory is RED until Task 2 (factory.py not yet created).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Task 1: channel instantiation + send() behaviour
# ---------------------------------------------------------------------------


async def test_log_channel_instantiates_and_sends() -> None:
    """LogNotificationChannel instantiates and send() completes without raising."""
    from src.notifications.log_channel import LogNotificationChannel

    ch = LogNotificationChannel()
    # send() must be awaitable and must not raise
    await ch.send(subject="Test subject", body="Test body")


async def test_log_channel_is_notification_channel() -> None:
    """LogNotificationChannel is a concrete NotificationChannel subclass."""
    from src.interfaces.notification_channel import NotificationChannel
    from src.notifications.log_channel import LogNotificationChannel

    assert issubclass(LogNotificationChannel, NotificationChannel)


async def test_telegram_channel_instantiates_and_sends() -> None:
    """TelegramNotificationChannel instantiates and send() posts to Bot API (patched)."""
    from src.notifications.telegram_channel import TelegramNotificationChannel

    ch = TelegramNotificationChannel(token="fake-token", chat_id="12345")

    # Patch aiohttp.ClientSession so no real HTTP call is made
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await ch.send(subject="Chiamata test", body="Riassunto breve.")


async def test_telegram_channel_non_200_does_not_raise() -> None:
    """TelegramNotificationChannel logs a warning on non-200 but does not raise."""
    from src.notifications.telegram_channel import TelegramNotificationChannel

    ch = TelegramNotificationChannel(token="fake-token", chat_id="12345")

    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        # must NOT raise, even on non-200
        await ch.send(subject="Test", body="Body")


async def test_email_channel_instantiates_and_sends() -> None:
    """EmailNotificationChannel instantiates and send() calls aiosmtplib (patched)."""
    from src.notifications.email_channel import EmailNotificationChannel

    ch = EmailNotificationChannel(
        host="smtp.example.com",
        port=587,
        user="user@example.com",
        password="secret",
        to="owner@example.com",
        from_="bot@example.com",
    )

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await ch.send(subject="Chiamata test", body="Riassunto.")
        mock_send.assert_called_once()


async def test_sms_channel_instantiates_and_sends() -> None:
    """SMSNotificationChannel instantiates and send() does NOT call any external API."""
    from src.notifications.sms_channel import SMSNotificationChannel

    ch = SMSNotificationChannel()
    # Must complete without raising and make no real network call
    await ch.send(subject="Chiamata test", body="Riassunto.")


async def test_sms_channel_no_http_calls() -> None:
    """SMSNotificationChannel.send() must not make any HTTP/network call (Phase 3 stub)."""
    from src.notifications.sms_channel import SMSNotificationChannel

    # Patch requests/aiohttp at the top level — if either is called, the test fails
    with patch("aiohttp.ClientSession") as mock_sess:
        ch = SMSNotificationChannel()
        await ch.send(subject="Test", body="Body")
        # ClientSession must NOT have been instantiated
        mock_sess.assert_not_called()


async def test_channels_are_notification_channel_subclasses() -> None:
    """All four concrete channels are proper NotificationChannel subclasses."""
    from src.interfaces.notification_channel import NotificationChannel
    from src.notifications.email_channel import EmailNotificationChannel
    from src.notifications.log_channel import LogNotificationChannel
    from src.notifications.sms_channel import SMSNotificationChannel
    from src.notifications.telegram_channel import TelegramNotificationChannel

    for cls in (
        LogNotificationChannel,
        TelegramNotificationChannel,
        EmailNotificationChannel,
        SMSNotificationChannel,
    ):
        assert issubclass(cls, NotificationChannel), (
            f"{cls.__name__} must subclass NotificationChannel"
        )


# ---------------------------------------------------------------------------
# Task 2: factory (RED — factory.py does not exist yet; these will fail)
# ---------------------------------------------------------------------------


async def test_factory_log_channel() -> None:
    """create_channel('log', tenant) returns LogNotificationChannel."""
    from src.notifications.factory import create_channel  # RED: factory absent
    from src.notifications.log_channel import LogNotificationChannel

    tenant = MagicMock()
    tenant.notification_channel = "log"

    ch = create_channel("log", tenant)
    assert isinstance(ch, LogNotificationChannel)


async def test_factory_telegram_channel() -> None:
    """create_channel('telegram', tenant) returns TelegramNotificationChannel."""
    from src.notifications.factory import create_channel  # RED: factory absent
    from src.notifications.telegram_channel import TelegramNotificationChannel

    tenant = MagicMock()
    tenant.notification_channel = "telegram"

    import os
    with patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "999"},
    ):
        ch = create_channel("telegram", tenant)
    assert isinstance(ch, TelegramNotificationChannel)


async def test_factory_unknown_falls_back_to_log() -> None:
    """create_channel with unknown name falls back to LogNotificationChannel (D-11)."""
    from src.notifications.factory import create_channel  # RED: factory absent
    from src.notifications.log_channel import LogNotificationChannel

    tenant = MagicMock()
    tenant.notification_channel = "unknown_channel"

    ch = create_channel("unknown_channel", tenant)
    assert isinstance(ch, LogNotificationChannel)


async def test_factory_none_falls_back_to_log() -> None:
    """create_channel(None, tenant) falls back to LogNotificationChannel (D-11)."""
    from src.notifications.factory import create_channel  # RED: factory absent
    from src.notifications.log_channel import LogNotificationChannel

    tenant = MagicMock()
    tenant.notification_channel = None

    ch = create_channel(None, tenant)
    assert isinstance(ch, LogNotificationChannel)
