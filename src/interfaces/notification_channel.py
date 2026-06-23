"""NotificationChannel interface seam (Phase 3 — end-of-call summary dispatch).

Defined now so later phases add concrete channels (Email/SMTP, SMS/WhatsApp,
Telegram, log) behind this interface, configurable per-tenant. Not functional in
Phase 1 — abstract stub only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationChannel(ABC):
    """A per-tenant outbound notification channel (Phase 3 seam)."""

    @abstractmethod
    async def send(self, subject: str, body: str) -> None:
        """Deliver a notification (e.g. end-of-call summary) to the recipient."""
        raise NotImplementedError
