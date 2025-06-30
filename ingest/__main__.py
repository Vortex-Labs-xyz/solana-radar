"""Main entry point for the ingest module."""
import asyncio
import logging
import os

from ingest.pump_ws import PumpWebSocketClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def main():
    """Main entry point for ingest service."""
    logger.info("Starting ingest service...")

    # Get configuration from environment
    kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    client = PumpWebSocketClient(kafka_servers=kafka_servers)

    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("Shutting down ingest service...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
