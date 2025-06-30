# Bitquery Kafka Consumer - Ingest Module

This module implements a Kafka consumer for ingesting real-time blockchain data from Bitquery streams, supporting both JSON and Protobuf message formats with SASL authentication (plain and SSL).

## Features

- **Multi-format Support**: Handles both JSON and Protobuf message formats
- **SASL Authentication**: Supports both SASL_PLAINTEXT and SASL_SSL
- **Deduplication**: Built-in Redis-based deduplication
- **Prometheus Metrics**: Exposes metrics for monitoring
- **Auto-reconnect**: Resilient connection handling

## Protobuf Support

The consumer automatically detects and processes Protobuf topics (ending with `.proto`):

### Supported Protobuf Topics

- `solana.dextrades.proto` - DEX trading events
- `solana.tokens.proto` - Token transfer events  
- `solana.transactions.proto` - Transaction data

### Topic Mapping

The consumer maps topics to their corresponding Protobuf message classes:

```python
TOPIC_MAP = {
    "solana.dextrades.proto": DexParsedBlockMessage,
    "solana.tokens.proto": TokenBlockMessage,
    "solana.transactions.proto": ParsedDexTransaction,
}
```

## SSL Configuration

For SASL_SSL connections, you need to provide SSL certificates.

### Certificate Setup

1. Create a `certs/` directory in the project root:
   ```bash
   mkdir certs
   ```

2. Place your PEM-formatted certificates in the `certs/` directory:
   - `client.key.pem` - Client private key
   - `client.cer.pem` - Client certificate
   - `server.cer.pem` - Server CA certificate

3. Set appropriate permissions:
   ```bash
   chmod 600 certs/*.pem
   ```

### Environment Variables

Configure the consumer using these environment variables:

#### Basic Configuration
```bash
# Kafka connection
KAFKA_BROKERS=kfk0.bitquery.io:9092,kfk1.bitquery.io:9092,kfk2.bitquery.io:9092
KAFKA_TOPICS=solana.dextrades.proto,solana.tokens.proto
KAFKA_GROUP_ID=my-consumer-group

# Authentication
KAFKA_SASL_USERNAME=your-username
KAFKA_SASL_PASSWORD=your-password
KAFKA_SECURITY_PROTOCOL=SASL_PLAINTEXT  # or SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-512

# Redis for deduplication
REDIS_URL=redis://localhost:6379

# Metrics
METRICS_PORT=8001
```

#### SSL Configuration (for SASL_SSL)
```bash
KAFKA_SECURITY_PROTOCOL=SASL_SSL
SSL_KEY_LOCATION=/etc/bitquery_certs/client.key.pem
SSL_CA_LOCATION=/etc/bitquery_certs/server.cer.pem
SSL_CERT_LOCATION=/etc/bitquery_certs/client.cer.pem
```

## Running the Consumer

### Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Compile Protobuf schemas:
   ```bash
   python scripts/compile_proto.py
   ```

3. Set environment variables:
   ```bash
   export KAFKA_BROKERS=kfk0.bitquery.io:9092
   export KAFKA_SASL_USERNAME=your-username
   export KAFKA_SASL_PASSWORD=your-password
   # ... other variables
   ```

4. Run the consumer:
   ```bash
   python -m ingest.bitquery_kafka
   ```

### Docker Compose

1. Create `.env` file from example:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

1. **Kopiere .env.example → .env und fülle deine Secrets aus:**
   ```bash
   cp .env.example .env
   # Öffne .env und ersetze alle Platzhalter wie <API_KEY> mit deinen echten Werten
   ```

2. For SASL_SSL, add certificate paths to `.env`:
   ```bash
   SSL_KEY_LOCATION=/etc/bitquery_certs/client.key.pem
   SSL_CA_LOCATION=/etc/bitquery_certs/server.cer.pem
   SSL_CERT_LOCATION=/etc/bitquery_certs/client.cer.pem
   ```

3. Start services:
   ```bash
   docker compose --profile ingest up
   ```

## Message Processing

### Protobuf Messages

When a Protobuf topic is detected:
1. Message bytes are parsed using the appropriate Protobuf class
2. Parsed message is converted to JSON using `MessageToDict`
3. JSON is sent to the output topic

### JSON Messages

Non-Protobuf topics are processed as JSON:
1. Bytes are decoded to UTF-8
2. JSON is parsed
3. Parsed data is sent to output topic

## Metrics

The consumer exposes Prometheus metrics on port 8001:

- `kafka_consumer_lag` - Consumer lag per topic/partition
- `events_ingested_total` - Total events processed per topic
- `dedup_hits` - Number of duplicate events detected
- `proto_decode_errors_total` - Protobuf decode errors per topic

Access metrics at: `http://localhost:8001/metrics`

## Troubleshooting

### Connection Issues

1. **SASL Authentication Failed**
   - Verify username/password
   - Check SASL mechanism matches server config
   - Ensure credentials have proper permissions

2. **SSL Connection Failed**
   - Verify certificate files exist and are readable
   - Check certificate validity
   - Ensure paths are correct in environment variables

3. **No Messages Received**
   - Check topic names are correct
   - Verify consumer group has access to topics
   - Check network connectivity to Kafka brokers

### Protobuf Errors

1. **Proto Decode Errors**
   - Check proto schemas are up to date
   - Verify topic mapping is correct
   - Monitor `proto_decode_errors_total` metric

2. **Missing Proto Classes**
   - Run `python scripts/compile_proto.py`
   - Ensure `bitquery_proto` directory exists
   - Check Python path includes proto modules

## Development

### Adding New Protobuf Topics

1. Add proto files to `proto/bitquery/solana/`
2. Update `TOPIC_MAP` in `bitquery_kafka.py`
3. Run `python scripts/compile_proto.py`
4. Add tests for new message types

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/test_bitquery_proto.py -v
```

## Performance Tuning

- Adjust consumer `fetch_max_bytes` for large messages
- Tune Redis connection pool for high throughput
- Monitor lag metrics and scale consumers as needed
- Use multiple consumer instances with same group ID for parallelism