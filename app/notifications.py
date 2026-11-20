from __future__ import annotations

import logging


class NotificationService:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.logger = logging.getLogger("notifications")

    def send(self, event: str, message: str) -> bool:
        if not self.enabled:
            return False
        self.logger.info("Notification event=%s message=%s", event, message)
        return True
