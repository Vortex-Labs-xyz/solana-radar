"""WebSocket client for pump.fun token data ingestion."""
import asyncio
import json
import logging
from typing import Optional

import websockets
from aiokafka import AIOKafkaProducer  # type: ignore
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)


class PumpWebSocketClient:
    """WebSocket client for pump.fun data ingestion."""

    def __init__(
        self,
        ws_url: str = "wss://pumpportal.fun/api/data",
        kafka_servers: str = "localhost:9092",
        kafka_topic: str = "pump.raw",
        reconnect_interval: int = 5,
        max_reconnect_interval: int = 300,
    ):
        """Initialize the WebSocket client.

        Args:
            ws_url: WebSocket URL to connect to
            kafka_servers: Kafka bootstrap servers
            kafka_topic: Kafka topic to publish messages to
            reconnect_interval: Initial reconnect interval in seconds
            max_reconnect_interval: Maximum reconnect interval in seconds
        """
        self.ws_url = ws_url
        self.kafka_servers = kafka_servers
        self.kafka_topic = kafka_topic
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_interval = max_reconnect_interval
        self.current_reconnect_interval = reconnect_interval
        self.producer: Optional[AIOKafkaProducer] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    async def _init_kafka_producer(self):
        """Initialize Kafka producer."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self.producer.start()
        logger.info(f"Kafka producer connected to {self.kafka_servers}")

    async def _cleanup_kafka_producer(self):
        """Cleanup Kafka producer."""
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer disconnected")

    async def _connect_websocket(self):
        """Connect to WebSocket with retry logic."""
        while True:
            try:
                logger.info(f"Connecting to WebSocket: {self.ws_url}")
                self.ws = await websockets.connect(self.ws_url)
                logger.info("WebSocket connected successfully")

                # Subscribe to new token events
                subscribe_msg = {"method": "subscribeNewToken"}
                await self.ws.send(json.dumps(subscribe_msg))
                logger.info("Subscribed to new token events")

                # Reset reconnect interval on successful connection
                self.current_reconnect_interval = self.reconnect_interval
                return

            except Exception as e:
                logger.error(f"Failed to connect to WebSocket: {e}")
                logger.info(f"Retrying in {self.current_reconnect_interval} seconds...")
                await asyncio.sleep(self.current_reconnect_interval)

                # Exponential backoff with max limit
                self.current_reconnect_interval = min(
                    self.current_reconnect_interval * 2, self.max_reconnect_interval
                )

    async def _process_message(self, message: str):
        """Process incoming WebSocket message.

        Args:
            message: Raw message string from WebSocket
        """
        try:
            data = json.loads(message)
            logger.debug(f"Received message: {data}")

            # Send to Kafka
            if self.producer:
                await self.producer.send(self.kafka_topic, value=data)
                logger.info(f"Sent message to Kafka topic '{self.kafka_topic}'")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def _handle_websocket(self):
        """Handle WebSocket connection and messages."""
        try:
            async for message in self.ws:
                await self._process_message(message)

        except ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in WebSocket handler: {e}")

    async def run(self):
        """Run the WebSocket client with automatic reconnection."""
        # Initialize Kafka producer
        await self._init_kafka_producer()

        try:
            while True:
                try:
                    # Connect to WebSocket
                    await self._connect_websocket()

                    # Handle messages
                    await self._handle_websocket()

                except KeyboardInterrupt:
                    logger.info("Received interrupt signal")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")

                logger.info(
                    f"Reconnecting in {self.current_reconnect_interval} seconds..."
                )
                await asyncio.sleep(self.current_reconnect_interval)

        finally:
            # Cleanup
            if self.ws and not self.ws.closed:
                await self.ws.close()
            await self._cleanup_kafka_producer()
            logger.info("WebSocket client shutdown complete")
