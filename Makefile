.PHONY: help lint test up down clean install

# Default target
help:
	@echo "Available targets:"
	@echo "  install  - Install Python dependencies"
	@echo "  lint     - Run linting tools (flake8, black, mypy)"
	@echo "  test     - Run tests with pytest"
	@echo "  up       - Start all services with docker-compose"
	@echo "  down     - Stop all services"
	@echo "  clean    - Clean up generated files and caches"

# Install dependencies
install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# Lint code
lint:
	@echo "Running flake8..."
	flake8 ingest/ core/ alerts/ tests/ --max-line-length=100 --exclude=__pycache__
	@echo "Running black..."
	black --check ingest/ core/ alerts/ tests/
	@echo "Running mypy..."
	mypy ingest/ core/ alerts/

# Run tests
test:
	@echo "Running pytest..."
	pytest tests/ -v --cov=ingest --cov=core --cov=alerts --cov-report=term-missing

# Start services
up:
	@echo "Starting services with docker-compose..."
	docker-compose --profile kafka --profile redis --profile monitoring up -d
	@echo "Services started. Kafka on :9092, Redis on :6379, Prometheus on :9090"

# Stop services
down:
	@echo "Stopping services..."
	docker-compose --profile kafka --profile redis --profile monitoring down

# Clean up
clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true 