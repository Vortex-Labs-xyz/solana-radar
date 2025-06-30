"""Deduplication service for alerts."""
import logging
from typing import Set

import redis

logger = logging.getLogger(__name__)


class DedupService:
    """Service for deduplicating alerts."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """Initialize deduplication service.

        Args:
            redis_url: Redis connection URL
        """
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.key_prefix = "alert:dedup:"
        self.ttl = 3600  # 1 hour TTL for dedup keys

    def _get_key(self, alert_type: str, identifier: str) -> str:
        """Generate Redis key for deduplication.

        Args:
            alert_type: Type of alert
            identifier: Unique identifier for the alert

        Returns:
            Redis key string
        """
        return f"{self.key_prefix}{alert_type}:{identifier}"

    def is_duplicate(self, alert_type: str, identifier: str) -> bool:
        """Check if an alert is a duplicate.

        Args:
            alert_type: Type of alert
            identifier: Unique identifier for the alert

        Returns:
            True if duplicate, False otherwise
        """
        key = self._get_key(alert_type, identifier)
        return bool(self.redis_client.exists(key))

    def mark_sent(self, alert_type: str, identifier: str) -> None:
        """Mark an alert as sent.

        Args:
            alert_type: Type of alert
            identifier: Unique identifier for the alert
        """
        key = self._get_key(alert_type, identifier)
        self.redis_client.setex(key, self.ttl, "1")
        logger.debug(f"Marked alert as sent: {key}")

    def should_send_alert(self, alert_type: str, identifier: str) -> bool:
        """Check if an alert should be sent.

        Args:
            alert_type: Type of alert
            identifier: Unique identifier for the alert

        Returns:
            True if alert should be sent, False if it's a duplicate
        """
        if self.is_duplicate(alert_type, identifier):
            logger.debug(f"Alert is duplicate: {alert_type}:{identifier}")
            return False
        return True


class AlertDedup:
    """Stub class for alert deduplication - to be implemented."""

    def __init__(self):
        """Initialize alert deduplication."""
        self.seen_alerts: Set[str] = set()
        logger.info("AlertDedup initialized (stub implementation)")

    def check_and_add(self, alert_id: str) -> bool:
        """Check if alert was already seen and add if not.

        Args:
            alert_id: Unique alert identifier

        Returns:
            True if alert is new, False if duplicate
        """
        if alert_id in self.seen_alerts:
            return False
        self.seen_alerts.add(alert_id)
        return True
