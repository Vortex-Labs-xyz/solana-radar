"""Tests for protobuf message processing in Bitquery Kafka consumer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bitquery_proto'))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from bitquery.solana import dex_block_message_pb2

from ingest.bitquery_kafka import BitqueryKafkaConsumer


@pytest.fixture
def consumer():
    """Create a BitqueryKafkaConsumer instance for testing."""
    return BitqueryKafkaConsumer(
        kafka_brokers="localhost:9092",
        kafka_topics="solana.dextrades.proto",
        kafka_group_id="test-group",
        kafka_sasl_username="test-user",
        kafka_sasl_password="test-pass",
    )


@pytest.fixture
def sample_proto_message():
    """Create a sample protobuf message for testing."""
    msg = dex_block_message_pb2.DexParsedBlockMessage()
    
    # Set block header
    msg.Header.Slot = 123456789
    msg.Header.Hash = b"test_hash_123"
    msg.Header.ParentSlot = 123456788
    msg.Header.Height = 987654321
    msg.Header.Timestamp = 1700000000
    
    # Add a transaction
    tx = msg.Transactions.add()
    tx.Index = 0
    tx.Signature = b"test_signature_456"
    tx.Status.Success = True
    tx.Header.Fee = 5000
    
    # Add a trade
    trade = tx.Trades.add()
    trade.InstructionIndex = 0
    trade.Dex.ProgramAddress = b"raydium_program"
    trade.Dex.ProtocolName = "Raydium"
    trade.Dex.ProtocolFamily = "AMM"
    trade.Buy.Amount = 1000000
    trade.Sell.Amount = 2000000
    trade.Fee = 1000
    
    return msg


def test_decode_protobuf_message_success(consumer, sample_proto_message):
    """Test successful decoding of a protobuf message."""
    # Serialize the message
    raw_bytes = sample_proto_message.SerializeToString()
    
    # Decode the message
    result = consumer._decode_protobuf_message("solana.dextrades.proto", raw_bytes)
    
    # Check the result
    assert result is not None
    assert isinstance(result, dict)
    assert "Header" in result
    assert result["Header"]["Slot"] == "123456789"
    assert "Transactions" in result
    assert len(result["Transactions"]) == 1
    assert result["Transactions"][0]["Status"]["Success"] is True


def test_decode_protobuf_message_unknown_topic(consumer):
    """Test decoding with an unknown topic."""
    raw_bytes = b"some_data"
    result = consumer._decode_protobuf_message("unknown.topic.proto", raw_bytes)
    assert result is None


def test_decode_protobuf_message_invalid_data(consumer):
    """Test decoding with invalid protobuf data."""
    raw_bytes = b"invalid_protobuf_data"
    result = consumer._decode_protobuf_message("solana.dextrades.proto", raw_bytes)
    assert result is None


@pytest.mark.asyncio
async def test_process_message_proto(consumer, sample_proto_message):
    """Test processing a protobuf message."""
    # Mock dependencies
    consumer.dedup_manager = AsyncMock()
    consumer.dedup_manager.is_new = AsyncMock(return_value=True)
    consumer.producer = AsyncMock()
    
    # Create a mock Kafka message
    mock_msg = MagicMock()
    mock_msg.topic = "solana.dextrades.proto"
    mock_msg.partition = 0
    mock_msg.offset = 100
    mock_msg.timestamp = 1700000000
    mock_msg.value = sample_proto_message.SerializeToString()
    
    # Process the message
    await consumer._process_message(mock_msg)
    
    # Verify the producer was called
    consumer.producer.send.assert_called_once()
    
    # Check the sent message
    call_args = consumer.producer.send.call_args
    assert call_args[0][0] == "bitquery.raw"  # topic
    sent_msg = call_args[1]["value"]
    
    assert sent_msg["topic"] == "solana.dextrades.proto"
    assert sent_msg["partition"] == 0
    assert sent_msg["offset"] == 100
    assert isinstance(sent_msg["data"], dict)
    assert "Header" in sent_msg["data"]
    assert "Transactions" in sent_msg["data"]


@pytest.mark.asyncio
async def test_process_message_json_fallback(consumer):
    """Test processing a JSON message (non-proto topic)."""
    # Mock dependencies
    consumer.dedup_manager = AsyncMock()
    consumer.dedup_manager.is_new = AsyncMock(return_value=True)
    consumer.producer = AsyncMock()
    
    # Create a mock Kafka message with JSON data
    json_data = '{"test": "data", "value": 123}'
    mock_msg = MagicMock()
    mock_msg.topic = "solana.dextrades"  # No .proto suffix
    mock_msg.partition = 0
    mock_msg.offset = 200
    mock_msg.timestamp = 1700000100
    mock_msg.value = json_data.encode("utf-8")
    
    # Process the message
    await consumer._process_message(mock_msg)
    
    # Verify the producer was called
    consumer.producer.send.assert_called_once()
    
    # Check the sent message
    call_args = consumer.producer.send.call_args
    sent_msg = call_args[1]["value"]
    
    assert sent_msg["topic"] == "solana.dextrades"
    assert sent_msg["data"]["test"] == "data"
    assert sent_msg["data"]["value"] == 123


def test_ssl_configuration():
    """Test SSL configuration for SASL_SSL."""
    consumer = BitqueryKafkaConsumer(
        kafka_brokers="localhost:9093",
        kafka_topics="test.topic",
        kafka_group_id="test-group",
        kafka_sasl_username="test-user",
        kafka_sasl_password="test-pass",
        kafka_security_protocol="SASL_SSL",
        ssl_key_location="/etc/certs/client.key",
        ssl_ca_location="/etc/certs/ca.pem",
        ssl_cert_location="/etc/certs/client.cert",
    )
    
    assert consumer.kafka_security_protocol == "SASL_SSL"
    assert consumer.ssl_key_location == "/etc/certs/client.key"
    assert consumer.ssl_ca_location == "/etc/certs/ca.pem"
    assert consumer.ssl_cert_location == "/etc/certs/client.cert"