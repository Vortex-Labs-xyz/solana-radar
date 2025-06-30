"""Redis-based deduplication manager for event processing."""
import logging
from typing import Optional

from redis import asyncio as aioredis  # type: ignore

logger = logging.getLogger(__name__)


class DedupManager:
    """Manages event deduplication using Redis."""

    def __init__(self, redis_url: str = "redis://localhost:6379", ttl: int = 120):
        """Initialize the deduplication manager.

        Args:
            redis_url: Redis connection URL
            ttl: Time-to-live for deduplication entries in seconds (default: 120)
        """
        self.redis_url = redis_url
        self.ttl = ttl
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        try:
            self._redis = await aioredis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            await self._redis.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")

    async def is_new(self, event_id: str) -> bool:
        """Check if an event is new (not seen before).

        Uses Redis SET with NX (only set if not exists) and EX (expiration).
        This is an atomic operation that both checks and sets in one command.

        Args:
            event_id: Unique identifier for the event

        Returns:
            True if the event is new, False if it's a duplicate
        """
        if not self._redis:
            logger.warning("Redis not connected, skipping deduplication")
            return True

        try:
            # SET key value NX EX seconds
            # NX: Only set if key doesn't exist
            # EX: Set expiration in seconds
            # Returns True if key was set, None if key already exists
            result = await self._redis.set(
                f"dedup:{event_id}", "1", nx=True, ex=self.ttl
            )
            return result is not None

        except Exception as e:
            logger.error(f"Error checking deduplication for {event_id}: {e}")
            # On error, assume event is new to avoid data loss
            return True

    async def mark_seen(self, event_id: str) -> None:
        """Mark an event as seen (for testing purposes).

        Args:
            event_id: Unique identifier for the event
        """
        if not self._redis:
            logger.warning("Redis not connected")
            return

        try:
            await self._redis.set(f"dedup:{event_id}", "1", ex=self.ttl)
        except Exception as e:
            logger.error(f"Error marking event as seen: {e}")

    async def clear(self) -> None:
        """Clear all deduplication entries (for testing purposes)."""
        if not self._redis:
            logger.warning("Redis not connected")
            return

        try:
            # Find all dedup keys
            keys = []
            async for key in self._redis.scan_iter("dedup:*"):
                keys.append(key)

            # Delete them if any exist
            if keys:
                await self._redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} deduplication entries")

        except Exception as e:
            logger.error(f"Error clearing deduplication entries: {e}")

    async def get_ttl(self, event_id: str) -> int:
        """Get remaining TTL for an event (for testing purposes).

        Args:
            event_id: Unique identifier for the event

        Returns:
            Remaining TTL in seconds, -1 if key doesn't exist, -2 if no TTL set
        """
        if not self._redis:
            return -1

        try:
            ttl = await self._redis.ttl(f"dedup:{event_id}")
            return ttl
        except Exception as e:
            logger.error(f"Error getting TTL for {event_id}: {e}")
            return -1
