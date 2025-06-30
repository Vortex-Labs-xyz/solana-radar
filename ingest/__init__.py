"""
Ingest module - Dummy aiokafka worker for real-time data ingestion
"""
import asyncio
import json
import logging
from typing import Optional
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class KafkaWorker:
    """Dummy Kafka worker for consuming messages"""
    
    def __init__(self, 
                 bootstrap_servers: str = 'localhost:9092',
                 topic: str = 'radar-events',
                 group_id: str = 'radar-consumer-group'):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.consumer: Optional[AIOKafkaConsumer] = None
        
    async def start(self):
        """Start the Kafka consumer"""
        try:
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=True
            )
            await self.consumer.start()
            logger.info(f"Kafka consumer started. Listening to topic: {self.topic}")
        except KafkaError as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise
            
    async def stop(self):
        """Stop the Kafka consumer"""
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")
            
    async def consume_messages(self):
        """Consume messages from Kafka"""
        if not self.consumer:
            raise RuntimeError("Consumer not started. Call start() first.")
            
        try:
            async for message in self.consumer:
                logger.info(f"Received message: {message.value}")
                # Process message here (dummy processing)
                await self._process_message(message.value)
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")
            raise
            
    async def _process_message(self, message: dict):
        """Process individual message (dummy implementation)"""
        # Simulate some processing
        await asyncio.sleep(0.1)
        logger.info(f"Processed message: {message.get('id', 'unknown')}")


async def main():
    """Main entry point for the worker"""
    # Get configuration from environment
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    
    worker = KafkaWorker(bootstrap_servers=bootstrap_servers)
    
    try:
        await worker.start()
        await worker.consume_messages()
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")
    finally:
        await worker.stop()


if __name__ == '__main__':
    asyncio.run(main()) 