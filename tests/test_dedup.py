"""Tests for Redis-based deduplication manager."""
import pytest
from unittest.mock import AsyncMock, patch

from core.dedup import DedupManager


@pytest.fixture
def dedup_manager():
    """Create a deduplication manager instance."""
    return DedupManager(redis_url="redis://localhost:6379", ttl=120)


@pytest.fixture
def connected_dedup_manager():
    """Create a connected deduplication manager with mocked Redis."""
    manager = DedupManager(redis_url="redis://localhost:6379", ttl=120)

    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=60)
    mock_redis.scan_iter = AsyncMock()
    mock_redis.delete = AsyncMock()

    # Set the mock redis directly
    manager._redis = mock_redis

    return manager, mock_redis


class TestDedupManager:
    """Test cases for DedupManager."""

    @pytest.mark.asyncio
    async def test_init(self):
        """Test initialization of DedupManager."""
        manager = DedupManager(redis_url="redis://test:6379", ttl=60)
        assert manager.redis_url == "redis://test:6379"
        assert manager.ttl == 60
        assert manager._redis is None

    @pytest.mark.asyncio
    async def test_connect_success(self, dedup_manager):
        """Test successful connection to Redis."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        async_from_url = AsyncMock(return_value=mock_redis)
        with patch("core.dedup.aioredis.from_url", async_from_url):
            await dedup_manager.connect()
            assert dedup_manager._redis is not None
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, dedup_manager):
        """Test connection failure to Redis."""
        with patch(
            "core.dedup.aioredis.from_url", side_effect=Exception("Connection failed")
        ):
            with pytest.raises(Exception, match="Connection failed"):
                await dedup_manager.connect()

    @pytest.mark.asyncio
    async def test_close_with_connection(self, connected_dedup_manager):
        """Test closing an active Redis connection."""
        manager, mock_redis = connected_dedup_manager
        await manager.close()
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_connection(self, dedup_manager):
        """Test closing when no connection exists."""
        # Should not raise any exception
        await dedup_manager.close()

    @pytest.mark.asyncio
    async def test_is_new_without_connection(self, dedup_manager):
        """Test is_new when Redis is not connected."""
        # Should return True and log warning
        result = await dedup_manager.is_new("event123")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_new_first_time(self, connected_dedup_manager):
        """Test is_new for a new event."""
        manager, mock_redis = connected_dedup_manager
        mock_redis.set.return_value = True

        result = await manager.is_new("event123")
        assert result is True

        mock_redis.set.assert_called_once_with("dedup:event123", "1", nx=True, ex=120)

    @pytest.mark.asyncio
    async def test_is_new_duplicate(self, connected_dedup_manager):
        """Test is_new for a duplicate event."""
        manager, mock_redis = connected_dedup_manager
        # Redis returns None when key already exists with nx=True
        mock_redis.set.return_value = None

        result = await manager.is_new("event123")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_new_redis_error(self, connected_dedup_manager):
        """Test is_new when Redis operation fails."""
        manager, mock_redis = connected_dedup_manager
        mock_redis.set.side_effect = Exception("Redis error")

        # Should return True on error to avoid data loss
        result = await manager.is_new("event123")
        assert result is True

    @pytest.mark.asyncio
    async def test_mark_seen_without_connection(self, dedup_manager):
        """Test mark_seen when Redis is not connected."""
        # Should not raise exception
        await dedup_manager.mark_seen("event123")

    @pytest.mark.asyncio
    async def test_mark_seen_success(self, connected_dedup_manager):
        """Test successfully marking an event as seen."""
        manager, mock_redis = connected_dedup_manager
        await manager.mark_seen("event123")

        mock_redis.set.assert_called_once_with("dedup:event123", "1", ex=120)

    @pytest.mark.asyncio
    async def test_mark_seen_error(self, connected_dedup_manager):
        """Test mark_seen when Redis operation fails."""
        manager, mock_redis = connected_dedup_manager
        mock_redis.set.side_effect = Exception("Redis error")

        # Should not raise exception
        await manager.mark_seen("event123")

    @pytest.mark.asyncio
    async def test_clear_without_connection(self, dedup_manager):
        """Test clear when Redis is not connected."""
        # Should not raise exception
        await dedup_manager.clear()

    @pytest.mark.asyncio
    async def test_clear_with_entries(self, connected_dedup_manager):
        """Test clearing deduplication entries."""
        manager, mock_redis = connected_dedup_manager

        # Create an async generator for scan_iter
        async def mock_scan_iter(pattern):
            for key in ["dedup:event1", "dedup:event2"]:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete = AsyncMock()

        await manager.clear()

        mock_redis.delete.assert_called_once_with("dedup:event1", "dedup:event2")

    @pytest.mark.asyncio
    async def test_clear_no_entries(self, connected_dedup_manager):
        """Test clearing when no entries exist."""
        manager, mock_redis = connected_dedup_manager

        # Create an async generator that yields nothing
        async def mock_scan_iter(pattern):
            return
            yield  # Make it a generator

        mock_redis.scan_iter = mock_scan_iter

        await manager.clear()

        # delete should not be called
        assert not mock_redis.delete.called

    @pytest.mark.asyncio
    async def test_clear_error(self, connected_dedup_manager):
        """Test clear when Redis operation fails."""
        manager, mock_redis = connected_dedup_manager

        # Create an async generator that raises error
        async def mock_scan_iter(pattern):
            raise Exception("Redis error")
            yield  # Make it a generator

        mock_redis.scan_iter = mock_scan_iter

        # Should not raise exception
        await manager.clear()

    @pytest.mark.asyncio
    async def test_get_ttl_without_connection(self, dedup_manager):
        """Test get_ttl when Redis is not connected."""
        ttl = await dedup_manager.get_ttl("event123")
        assert ttl == -1

    @pytest.mark.asyncio
    async def test_get_ttl_existing_key(self, connected_dedup_manager):
        """Test get_ttl for an existing key."""
        manager, mock_redis = connected_dedup_manager
        mock_redis.ttl = AsyncMock(return_value=60)

        ttl = await manager.get_ttl("event123")
        assert ttl == 60

        mock_redis.ttl.assert_called_once_with("dedup:event123")

    @pytest.mark.asyncio
    async def test_get_ttl_non_existing_key(self, connected_dedup_manager):
        """Test get_ttl for a non-existing key."""
        manager, mock_redis = connected_dedup_manager
        mock_redis.ttl = AsyncMock(return_value=-1)

        ttl = await manager.get_ttl("event123")
        assert ttl == -1

    @pytest.mark.asyncio
    async def test_get_ttl_error(self, connected_dedup_manager):
        """Test get_ttl when Redis operation fails."""
        manager, mock_redis = connected_dedup_manager
        mock_redis.ttl = AsyncMock(side_effect=Exception("Redis error"))

        ttl = await manager.get_ttl("event123")
        assert ttl == -1


@pytest.mark.asyncio
async def test_dedup_manager_integration():
    """Integration test with all operations."""
    manager = DedupManager(ttl=2)  # Short TTL for testing

    # Test without connection
    assert await manager.is_new("test1") is True

    # Mock connection
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.set = AsyncMock(
        side_effect=[True, None, True]
    )  # First new, then dup, then new
    mock_redis.ttl = AsyncMock(return_value=1)
    mock_redis.close = AsyncMock()

    async_from_url = AsyncMock(return_value=mock_redis)
    with patch("core.dedup.aioredis.from_url", async_from_url):
        await manager.connect()

        # First event should be new
        assert await manager.is_new("test1") is True

        # Same event should be duplicate
        assert await manager.is_new("test1") is False

        # Different event should be new
        assert await manager.is_new("test2") is True

        # Check TTL
        ttl = await manager.get_ttl("test1")
        assert ttl == 1

        await manager.close()
