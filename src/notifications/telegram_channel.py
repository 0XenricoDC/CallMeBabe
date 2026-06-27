"""TelegramNotificationChannel — real Telegram Bot API notification channel (D-10).

Posts the end-of-call summary to a Telegram chat via the Bot sendMessage API
using aiohttp (already a transitive dep of pipecat — no extra install needed).

Security:
- T-03-NINJ: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID come only from env (via
  constructor args sourced from os.getenv in the factory). Zero influence from
  caller args or the transcript.
- T-03-LOGPII: on send failure, only the HTTP status code and exception type are
  logged — never the message subject or body.
- T-03-TOK: token stored only in the constructor; never hardcoded or logged.
"""

from __future__ import annotations

from loguru import logger

from src.interfaces.notification_channel import NotificationChannel

_TELEGRAM_API_BASE = "https://api.telegram.org/bot"
_TIMEOUT_SECS = 10


class TelegramNotificationChannel(NotificationChannel):
    """Send the call summary to a Telegram chat via the Bot sendMessage API (D-10 REAL).

    Credentials must come from environment variables, resolved by the factory and
    passed as constructor arguments. The channel never reads ``os.getenv`` itself —
    that responsibility belongs to the factory (T-injection isolation).

    Args:
        token:   Telegram Bot API token from TELEGRAM_BOT_TOKEN env var.
        chat_id: Destination chat id from TELEGRAM_CHAT_ID env var.
    """

    def __init__(self, token: str, chat_id: str) -> None:
        # Security: only store the token/chat_id passed by the factory (from env).
        # Never accept from caller input.
        self._token = token
        self._chat_id = chat_id

    async def send(self, subject: str, body: str) -> None:
        """Post a Telegram message with subject and body via Bot API sendMessage.

        Args:
            subject: Notification subject line.
            body:    2-3 sentence Italian call summary.
        """
        import aiohttp  # noqa: PLC0415 — already a pipecat transitive dep

        url = f"{_TELEGRAM_API_BASE}{self._token}/sendMessage"
        text = f"*{subject}*\n\n{body}"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=_TIMEOUT_SECS),
                ) as resp:
                    if resp.status != 200:
                        # Security (T-03-LOGPII): log status code only — never body/subject.
                        logger.warning(
                            f"TelegramNotificationChannel.send: non-200 response "
                            f"(status={resp.status})"
                        )
        except Exception as exc:  # noqa: BLE001
            # Security (T-03-LOGPII): NEVER log subject/body (may contain PII).
            logger.error(
                f"TelegramNotificationChannel.send failed: {type(exc).__name__}"
            )
