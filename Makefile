.PHONY: help lint test compose-up compose-down clean

# Default target
help:
	@echo "Available targets:"
	@echo "  lint         - Run linting (black, flake8, mypy)"
	@echo "  test         - Run tests with pytest"
	@echo "  compose-up   - Start Docker Compose services"
	@echo "  compose-down - Stop Docker Compose services"
	@echo "  clean        - Clean up generated files"

# Install dependencies
install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# Lint code
lint:
	@echo "Running black formatter check..."
	black --check ingest/ core/ alerts/ tests/
	@echo "Running flake8..."
	flake8 ingest/ core/ alerts/ tests/ --max-line-length=120 --exclude=__pycache__
	@echo "Running mypy type checker..."
	mypy ingest/ core/ alerts/

# Run tests
test:
	@echo "Running pytest..."
	pytest tests/ -v

# Start services
compose-up:
	@echo "Starting Docker Compose services (ingest profile)..."
	docker compose --profile ingest up -d

# Stop services
compose-down:
	@echo "Stopping Docker Compose services..."
	docker compose down

# Clean up
clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} + 