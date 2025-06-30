"""Tests for Bitquery Kafka consumer."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ingest.bitquery_kafka import BitqueryKafkaConsumer, main


@pytest.fixture
def kafka_consumer():
    """Create a Bitquery Kafka consumer instance."""
    return BitqueryKafkaConsumer(
        kafka_brokers="broker1:9092,broker2:9092",
        kafka_topics="topic1,topic2",
        kafka_group_id="test-group",
        kafka_sasl_username="testuser",
        kafka_sasl_password="testpass",
        redis_url="redis://localhost:6379",
    )


class TestBitqueryKafkaConsumer:
    """Test cases for BitqueryKafkaConsumer."""

    @pytest.mark.asyncio
    async def test_init(self):
        """Test initialization of BitqueryKafkaConsumer."""
        consumer = BitqueryKafkaConsumer(
            kafka_brokers="broker1:9092,broker2:9092",
            kafka_topics="topic1,topic2,topic3",
            kafka_group_id="test-group",
            kafka_sasl_username="user",
            kafka_sasl_password="pass",
            output_topic="output.topic",
        )

        assert consumer.kafka_brokers == "broker1:9092,broker2:9092"
        assert consumer.kafka_topics == ["topic1", "topic2", "topic3"]
        assert consumer.kafka_group_id == "test-group"
        assert consumer.kafka_sasl_username == "user"
        assert consumer.kafka_sasl_password == "pass"
        assert consumer.output_topic == "output.topic"
        assert consumer.consumer is None
        assert consumer.producer is None
        assert consumer.dedup_manager is None
        assert consumer._running is False

    @patch("ingest.bitquery_kafka.AIOKafkaConsumer")
    @pytest.mark.asyncio
    async def test_init_kafka_consumer(self, mock_consumer_class, kafka_consumer):
        """Test Kafka consumer initialization."""
        mock_consumer = AsyncMock()
        mock_consumer.start = AsyncMock()
        mock_consumer_class.return_value = mock_consumer

        await kafka_consumer._init_kafka_consumer()

        mock_consumer_class.assert_called_once_with(
            "topic1",
            "topic2",
            bootstrap_servers="broker1:9092,broker2:9092",
            group_id="test-group",
            security_protocol="SASL_PLAINTEXT",
            sasl_mechanism="SCRAM-SHA-512",
            sasl_plain_username="testuser",
            sasl_plain_password="testpass",
            enable_auto_commit=True,
            auto_offset_reset="latest",
            value_deserializer=mock_consumer_class.call_args[1]["value_deserializer"],
        )
        mock_consumer.start.assert_called_once()
        assert kafka_consumer.consumer == mock_consumer

    @patch("ingest.bitquery_kafka.AIOKafkaProducer")
    @pytest.mark.asyncio
    async def test_init_kafka_producer(self, mock_producer_class, kafka_consumer):
        """Test Kafka producer initialization."""
        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer_class.return_value = mock_producer

        await kafka_consumer._init_kafka_producer()

        mock_producer.start.assert_called_once()
        assert kafka_consumer.producer == mock_producer

    @patch("ingest.bitquery_kafka.DedupManager")
    @pytest.mark.asyncio
    async def test_init_dedup_manager(self, mock_dedup_class, kafka_consumer):
        """Test deduplication manager initialization."""
        mock_dedup = AsyncMock()
        mock_dedup.connect = AsyncMock()
        mock_dedup_class.return_value = mock_dedup

        await kafka_consumer._init_dedup_manager()

        mock_dedup_class.assert_called_once_with(redis_url="redis://localhost:6379")
        mock_dedup.connect.assert_called_once()
        assert kafka_consumer.dedup_manager == mock_dedup

    @pytest.mark.asyncio
    async def test_cleanup_all_resources(self, kafka_consumer):
        """Test cleanup of all resources."""
        # Mock all resources
        kafka_consumer.consumer = AsyncMock()
        kafka_consumer.producer = AsyncMock()
        kafka_consumer.dedup_manager = AsyncMock()

        await kafka_consumer._cleanup()

        kafka_consumer.consumer.stop.assert_called_once()
        kafka_consumer.producer.stop.assert_called_once()
        kafka_consumer.dedup_manager.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_resources(self, kafka_consumer):
        """Test cleanup when no resources are initialized."""
        # Should not raise any exception
        await kafka_consumer._cleanup()

    @patch("ingest.bitquery_kafka.kafka_lag")
    @pytest.mark.asyncio
    async def test_update_metrics(self, mock_kafka_lag, kafka_consumer):
        """Test Prometheus metrics update."""
        # Mock consumer with partitions
        mock_tp = MagicMock()
        mock_tp.topic = "topic1"
        mock_tp.partition = 0

        # Create proper async mocks
        kafka_consumer.consumer = AsyncMock()
        kafka_consumer.consumer.assignment = MagicMock(return_value=[mock_tp])
        kafka_consumer.consumer.position = AsyncMock(return_value=100)
        kafka_consumer.consumer.end_offsets = AsyncMock(return_value={mock_tp: 150})

        mock_gauge = MagicMock()
        mock_kafka_lag.labels.return_value = mock_gauge

        await kafka_consumer._update_metrics()

        kafka_consumer.consumer.assignment.assert_called_once()
        kafka_consumer.consumer.position.assert_called_once_with(mock_tp)
        kafka_consumer.consumer.end_offsets.assert_called_once()
        mock_kafka_lag.labels.assert_called_once_with(topic="topic1", partition=0)
        mock_gauge.set.assert_called_once_with(50)  # lag = 150 - 100

    @pytest.mark.asyncio
    async def test_update_metrics_no_consumer(self, kafka_consumer):
        """Test metrics update when consumer is not initialized."""
        # Should not raise exception
        await kafka_consumer._update_metrics()

    @pytest.mark.asyncio
    async def test_update_metrics_error(self, kafka_consumer):
        """Test metrics update when error occurs."""
        kafka_consumer.consumer = AsyncMock()
        kafka_consumer.consumer.assignment.side_effect = Exception("Metrics error")

        # Should not raise exception
        await kafka_consumer._update_metrics()

    @patch("ingest.bitquery_kafka.events_ingested_total")
    @patch("ingest.bitquery_kafka.dedup_hits")
    @pytest.mark.asyncio
    async def test_process_message_new_event(
        self, mock_dedup_hits, mock_events_total, kafka_consumer
    ):
        """Test processing a new message."""
        # Setup mocks
        kafka_consumer.dedup_manager = AsyncMock()
        kafka_consumer.dedup_manager.is_new.return_value = True
        kafka_consumer.producer = AsyncMock()

        mock_counter = MagicMock()
        mock_events_total.labels.return_value = mock_counter

        # Create mock message
        mock_msg = MagicMock()
        mock_msg.topic = "topic1"
        mock_msg.partition = 0
        mock_msg.offset = 123
        mock_msg.timestamp = 1234567890
        mock_msg.value = b'{"test": "data"}'

        await kafka_consumer._process_message(mock_msg)

        # Verify deduplication check
        kafka_consumer.dedup_manager.is_new.assert_called_once_with("topic1:0:123")

        # Verify message sent to producer
        expected_output = {
            "topic": "topic1",
            "partition": 0,
            "offset": 123,
            "timestamp": 1234567890,
            "data": {"test": "data"},
        }
        kafka_consumer.producer.send.assert_called_once_with(
            "bitquery.raw", value=expected_output
        )

        # Verify metrics
        mock_events_total.labels.assert_called_once_with(topic="topic1")
        mock_counter.inc.assert_called_once()

    @patch("ingest.bitquery_kafka.dedup_hits")
    @pytest.mark.asyncio
    async def test_process_message_duplicate(self, mock_dedup_hits, kafka_consumer):
        """Test processing a duplicate message."""
        # Setup mocks
        kafka_consumer.dedup_manager = AsyncMock()
        kafka_consumer.dedup_manager.is_new.return_value = False
        kafka_consumer.producer = AsyncMock()

        # Create mock message
        mock_msg = MagicMock()
        mock_msg.topic = "topic1"
        mock_msg.partition = 0
        mock_msg.offset = 123
        mock_msg.value = b'{"test": "data"}'

        await kafka_consumer._process_message(mock_msg)

        # Verify deduplication hit
        mock_dedup_hits.inc.assert_called_once()

        # Verify message NOT sent to producer
        kafka_consumer.producer.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_invalid_json(self, kafka_consumer):
        """Test processing a message with invalid JSON."""
        kafka_consumer.dedup_manager = AsyncMock()
        kafka_consumer.dedup_manager.is_new.return_value = True
        kafka_consumer.producer = AsyncMock()

        # Create mock message with invalid JSON
        mock_msg = MagicMock()
        mock_msg.topic = "topic1"
        mock_msg.partition = 0
        mock_msg.offset = 123
        mock_msg.timestamp = 1234567890
        mock_msg.value = b"invalid json"

        await kafka_consumer._process_message(mock_msg)

        # Should still process as raw data
        expected_output = {
            "topic": "topic1",
            "partition": 0,
            "offset": 123,
            "timestamp": 1234567890,
            "data": {"raw": "invalid json"},
        }
        kafka_consumer.producer.send.assert_called_once_with(
            "bitquery.raw", value=expected_output
        )

    @pytest.mark.asyncio
    async def test_process_message_error(self, kafka_consumer):
        """Test process_message when error occurs."""
        kafka_consumer.dedup_manager = AsyncMock()
        kafka_consumer.dedup_manager.is_new.side_effect = Exception("Process error")

        mock_msg = MagicMock()
        mock_msg.topic = "topic1"
        mock_msg.value = b'{"test": "data"}'

        # Should not raise exception
        await kafka_consumer._process_message(mock_msg)

    @pytest.mark.asyncio
    async def test_metrics_loop(self, kafka_consumer):
        """Test the metrics update loop."""
        kafka_consumer._running = True
        kafka_consumer._update_metrics = AsyncMock()

        # Create a task that stops after 2 iterations
        async def stop_after_delay():
            await asyncio.sleep(0.1)
            kafka_consumer._running = False

        stop_task = asyncio.create_task(stop_after_delay())

        await kafka_consumer._metrics_loop()

        await stop_task

        # Should have called update_metrics at least once
        assert kafka_consumer._update_metrics.call_count >= 1


@patch("ingest.bitquery_kafka.os.getenv")
def test_main_missing_credentials(mock_getenv):
    """Test main function when credentials are missing."""
    mock_getenv.side_effect = lambda key, default="": {
        "KAFKA_BROKERS": "localhost:9092",
        "KAFKA_SASL_USERNAME": "",  # Empty username
        "KAFKA_SASL_PASSWORD": "pass",
    }.get(key, default)

    # Should return without running
    with patch("ingest.bitquery_kafka.asyncio.run") as mock_run:
        main()
        mock_run.assert_not_called()


@patch("ingest.bitquery_kafka.os.getenv")
@patch("ingest.bitquery_kafka.asyncio.run")
def test_main_with_credentials(mock_run, mock_getenv):
    """Test main function with valid credentials."""
    mock_getenv.side_effect = lambda key, default="": {
        "KAFKA_BROKERS": "broker1:9092",
        "KAFKA_TOPICS": "topic1,topic2",
        "KAFKA_GROUP_ID": "test-group",
        "KAFKA_SASL_USERNAME": "user",
        "KAFKA_SASL_PASSWORD": "pass",
        "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
        "KAFKA_SASL_MECHANISM": "PLAIN",
        "REDIS_URL": "redis://redis:6379",
        "SSL_KEY_LOCATION": "/tmp/client.key",
        "SSL_CA_LOCATION": "/tmp/ca.pem",
        "SSL_CERT_LOCATION": "/tmp/client.cert",
    }.get(key, default)

    main()

    # Verify asyncio.run was called
    mock_run.assert_called_once()

    # Get the coroutine that was passed to asyncio.run
    coro = mock_run.call_args[0][0]
    assert coro.__name__ == "run"


@patch("ingest.bitquery_kafka.AIOKafkaConsumer")
@pytest.mark.asyncio
async def test_init_kafka_consumer_with_ssl(mock_consumer_class):
    """Test Kafka consumer initialization with SSL."""
    mock_consumer = AsyncMock()
    mock_consumer.start = AsyncMock()
    mock_consumer_class.return_value = mock_consumer

    # Create consumer with SSL configuration
    consumer = BitqueryKafkaConsumer(
        kafka_brokers="broker1:9093",
        kafka_topics="topic1",
        kafka_group_id="test-group",
        kafka_sasl_username="user",
        kafka_sasl_password="pass",
        kafka_security_protocol="SASL_SSL",
        ssl_key_location="/tmp/client.key",
        ssl_ca_location="/tmp/ca.pem",
        ssl_cert_location="/tmp/client.cert",
    )

    await consumer._init_kafka_consumer()

    # Verify SSL parameters were passed
    call_kwargs = mock_consumer_class.call_args[1]
    assert call_kwargs["security_protocol"] == "SASL_SSL"
    assert call_kwargs["ssl_keyfile"] == "/tmp/client.key"
    assert call_kwargs["ssl_cafile"] == "/tmp/ca.pem"
    assert call_kwargs["ssl_certfile"] == "/tmp/client.cert"
