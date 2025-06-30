"""Bitquery Kafka consumer for real-time data ingestion."""
import asyncio
import json
import logging
import os
import sys
from typing import Optional, Dict, Any

# Add path for protobuf imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bitquery_proto"))

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore # noqa: E402
from prometheus_client import Counter, Gauge, start_http_server  # type: ignore # noqa: E402
from google.protobuf.json_format import MessageToDict  # noqa: E402

from core.dedup import DedupManager  # noqa: E402

# Import protobuf message classes
from bitquery.solana import (  # noqa: E402
    dex_block_message_pb2,
    token_block_message_pb2,
)

logger = logging.getLogger(__name__)

# Prometheus metrics
kafka_lag = Gauge("kafka_consumer_lag", "Kafka consumer lag", ["topic", "partition"])
events_ingested_total = Counter(
    "events_ingested_total", "Total events ingested", ["topic"]
)
dedup_hits = Counter("dedup_hits", "Number of duplicate events detected")
proto_decode_errors_total = Counter(
    "proto_decode_errors_total", "Total protobuf decode errors", ["topic"]
)

# Topic to protobuf message class mapping
TOPIC_MAP: Dict[str, type] = {
    "solana.dextrades.proto": dex_block_message_pb2.DexParsedBlockMessage,
    "solana.tokens.proto": token_block_message_pb2.TokenBlockMessage,
    "solana.transactions.proto": dex_block_message_pb2.ParsedDexTransaction,
}


class BitqueryKafkaConsumer:
    """Kafka consumer for Bitquery real-time data."""

    def __init__(
        self,
        kafka_brokers: str,
        kafka_topics: str,
        kafka_group_id: str,
        kafka_sasl_username: str,
        kafka_sasl_password: str,
        kafka_security_protocol: str = "SASL_PLAINTEXT",
        kafka_sasl_mechanism: str = "SCRAM-SHA-512",
        output_topic: str = "bitquery.raw",
        redis_url: str = "redis://localhost:6379",
        ssl_key_location: Optional[str] = None,
        ssl_ca_location: Optional[str] = None,
        ssl_cert_location: Optional[str] = None,
    ):
        """Initialize the Bitquery Kafka consumer.

        Args:
            kafka_brokers: Comma-separated list of Kafka brokers
            kafka_topics: Comma-separated list of topics to consume
            kafka_group_id: Consumer group ID
            kafka_sasl_username: SASL username for authentication
            kafka_sasl_password: SASL password for authentication
            kafka_security_protocol: Security protocol (default: SASL_PLAINTEXT)
            kafka_sasl_mechanism: SASL mechanism (default: SCRAM-SHA-512)
            output_topic: Topic to publish deduplicated messages
            redis_url: Redis connection URL
            ssl_key_location: Path to SSL key file (for SASL_SSL)
            ssl_ca_location: Path to SSL CA file (for SASL_SSL)
            ssl_cert_location: Path to SSL certificate file (for SASL_SSL)
        """
        self.kafka_brokers = kafka_brokers
        self.kafka_topics = kafka_topics.split(",")
        self.kafka_group_id = kafka_group_id
        self.kafka_sasl_username = kafka_sasl_username
        self.kafka_sasl_password = kafka_sasl_password
        self.kafka_security_protocol = kafka_security_protocol
        self.kafka_sasl_mechanism = kafka_sasl_mechanism
        self.output_topic = output_topic
        self.redis_url = redis_url
        self.ssl_key_location = ssl_key_location
        self.ssl_ca_location = ssl_ca_location
        self.ssl_cert_location = ssl_cert_location

        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.dedup_manager: Optional[DedupManager] = None
        self._running = False

    async def _init_kafka_consumer(self):
        """Initialize Kafka consumer with SCRAM authentication."""
        consumer_config = {
            "bootstrap_servers": self.kafka_brokers,
            "group_id": self.kafka_group_id,
            "security_protocol": self.kafka_security_protocol,
            "sasl_mechanism": self.kafka_sasl_mechanism,
            "sasl_plain_username": self.kafka_sasl_username,
            "sasl_plain_password": self.kafka_sasl_password,
            "enable_auto_commit": True,
            "auto_offset_reset": "latest",
            "value_deserializer": lambda v: v,  # Keep raw bytes
        }

        # Add SSL configuration if using SASL_SSL
        if self.kafka_security_protocol == "SASL_SSL":
            if self.ssl_key_location:
                consumer_config["ssl_keyfile"] = self.ssl_key_location
            if self.ssl_ca_location:
                consumer_config["ssl_cafile"] = self.ssl_ca_location
            if self.ssl_cert_location:
                consumer_config["ssl_certfile"] = self.ssl_cert_location

        self.consumer = AIOKafkaConsumer(*self.kafka_topics, **consumer_config)
        await self.consumer.start()
        logger.info(
            f"Kafka consumer connected to {self.kafka_brokers}, "
            f"topics: {self.kafka_topics}"
        )

    async def _init_kafka_producer(self):
        """Initialize Kafka producer for output topic."""
        # Use local Kafka broker for output
        local_broker = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.producer = AIOKafkaProducer(
            bootstrap_servers=local_broker,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
            if isinstance(v, dict)
            else v,
        )
        await self.producer.start()
        logger.info(
            f"Kafka producer connected to {local_broker} for topic: {self.output_topic}"
        )

    async def _init_dedup_manager(self):
        """Initialize deduplication manager."""
        self.dedup_manager = DedupManager(redis_url=self.redis_url)
        await self.dedup_manager.connect()
        logger.info("Deduplication manager initialized")

    async def _cleanup(self):
        """Cleanup resources."""
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer disconnected")

        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer disconnected")

        if self.dedup_manager:
            await self.dedup_manager.close()
            logger.info("Deduplication manager closed")

    async def _update_metrics(self):
        """Update Prometheus metrics for consumer lag."""
        if not self.consumer:
            return

        try:
            # Get current positions
            partitions = self.consumer.assignment()
            if not partitions:
                return

            # Get end offsets
            end_offsets = await self.consumer.end_offsets(partitions)

            # Calculate lag for each partition
            for tp in partitions:
                position = await self.consumer.position(tp)
                end_offset = end_offsets.get(tp, 0)
                lag = end_offset - position if end_offset > position else 0
                kafka_lag.labels(topic=tp.topic, partition=tp.partition).set(lag)

        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def _decode_protobuf_message(
        self, topic: str, raw_bytes: bytes
    ) -> Optional[Dict[str, Any]]:
        """Decode protobuf message based on topic.

        Args:
            topic: The topic name
            raw_bytes: Raw protobuf bytes

        Returns:
            Decoded message as dict or None if decoding fails
        """
        if topic not in TOPIC_MAP:
            return None

        try:
            message_class = TOPIC_MAP[topic]
            msg_obj = message_class()
            msg_obj.ParseFromString(raw_bytes)
            return MessageToDict(msg_obj)
        except Exception as e:
            logger.error(f"Error decoding protobuf for topic {topic}: {e}")
            proto_decode_errors_total.labels(topic=topic).inc()
            return None

    async def _process_message(self, msg):
        """Process a single Kafka message.

        Args:
            msg: Kafka message
        """
        try:
            # Extract message data
            topic = msg.topic
            value = msg.value

            # Check if topic is a protobuf topic
            if topic.endswith(".proto"):
                # Decode protobuf
                data = self._decode_protobuf_message(topic, value)
                if data is None:
                    logger.error(
                        f"Failed to decode protobuf message from topic {topic}"
                    )
                    return
            else:
                # JSON path (unchanged)
                if isinstance(value, bytes):
                    value = value.decode("utf-8")

                # Parse JSON if possible
                try:
                    data = json.loads(value)
                except json.JSONDecodeError:
                    data = {"raw": value}

            # Generate event ID from message
            event_id = f"{topic}:{msg.partition}:{msg.offset}"

            # Check deduplication
            if self.dedup_manager and not await self.dedup_manager.is_new(event_id):
                dedup_hits.inc()
                logger.debug(f"Duplicate event detected: {event_id}")
                return

            # Prepare output message
            output_msg = {
                "topic": topic,
                "partition": msg.partition,
                "offset": msg.offset,
                "timestamp": msg.timestamp,
                "data": data,
            }

            # Send to output topic
            if self.producer:
                await self.producer.send(self.output_topic, value=output_msg)
                events_ingested_total.labels(topic=topic).inc()
                logger.debug(f"Sent message to {self.output_topic}: {event_id}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def run(self):
        """Run the Kafka consumer."""
        # Initialize components
        await self._init_dedup_manager()
        await self._init_kafka_producer()
        await self._init_kafka_consumer()

        self._running = True
        metrics_task = None

        try:
            # Start metrics update task
            metrics_task = asyncio.create_task(self._metrics_loop())

            logger.info("Starting message consumption...")
            async for msg in self.consumer:
                if not self._running:
                    break
                await self._process_message(msg)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error in consumer loop: {e}")
            raise
        finally:
            self._running = False
            if metrics_task:
                metrics_task.cancel()
                try:
                    await metrics_task
                except asyncio.CancelledError:
                    pass
            await self._cleanup()
            logger.info("Bitquery Kafka consumer shutdown complete")

    async def _metrics_loop(self):
        """Periodically update metrics."""
        while self._running:
            await self._update_metrics()
            await asyncio.sleep(10)  # Update every 10 seconds


def main():
    """Main entry point for Bitquery Kafka consumer."""
    # Get configuration from environment
    kafka_brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    kafka_topics = os.getenv("KAFKA_TOPICS", "solana.dextrades.proto")
    kafka_group_id = os.getenv("KAFKA_GROUP_ID", "solana-radar")
    kafka_sasl_username = os.getenv("KAFKA_SASL_USERNAME", "")
    kafka_sasl_password = os.getenv("KAFKA_SASL_PASSWORD", "")
    kafka_security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT")
    kafka_sasl_mechanism = os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    metrics_port = int(os.getenv("METRICS_PORT", "8001"))

    # SSL configuration for SASL_SSL
    ssl_key_location = os.getenv("SSL_KEY_LOCATION")
    ssl_ca_location = os.getenv("SSL_CA_LOCATION")
    ssl_cert_location = os.getenv("SSL_CERT_LOCATION")

    # Validate required environment variables
    if not kafka_sasl_username or not kafka_sasl_password:
        logger.error("KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD are required")
        return

    # Start Prometheus metrics server
    start_http_server(metrics_port)
    logger.info(f"Started Prometheus metrics server on port {metrics_port}")

    consumer = BitqueryKafkaConsumer(
        kafka_brokers=kafka_brokers,
        kafka_topics=kafka_topics,
        kafka_group_id=kafka_group_id,
        kafka_sasl_username=kafka_sasl_username,
        kafka_sasl_password=kafka_sasl_password,
        kafka_security_protocol=kafka_security_protocol,
        kafka_sasl_mechanism=kafka_sasl_mechanism,
        redis_url=redis_url,
        ssl_key_location=ssl_key_location,
        ssl_ca_location=ssl_ca_location,
        ssl_cert_location=ssl_cert_location,
    )

    asyncio.run(consumer.run())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    main()
