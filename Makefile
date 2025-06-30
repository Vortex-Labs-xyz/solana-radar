.PHONY: help lint test compose-up compose-down clean

# Detect if we're in a virtual environment or if one exists
PYTHON := $(if $(VIRTUAL_ENV),python,$(if $(wildcard venv/bin/python),venv/bin/python,python3))
PIP := $(if $(VIRTUAL_ENV),pip,$(if $(wildcard venv/bin/pip),venv/bin/pip,pip3))
BLACK := $(if $(VIRTUAL_ENV),black,$(if $(wildcard venv/bin/black),venv/bin/black,black))
FLAKE8 := $(if $(VIRTUAL_ENV),flake8,$(if $(wildcard venv/bin/flake8),venv/bin/flake8,flake8))
MYPY := $(if $(VIRTUAL_ENV),mypy,$(if $(wildcard venv/bin/mypy),venv/bin/mypy,mypy))
PYTEST := $(if $(VIRTUAL_ENV),pytest,$(if $(wildcard venv/bin/pytest),venv/bin/pytest,pytest))

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
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

# Lint code
lint:
	@echo "Running black formatter check..."
	$(BLACK) --check ingest/ core/ alerts/ tests/
	@echo "Running flake8..."
	$(FLAKE8) ingest/ core/ alerts/ tests/ --max-line-length=120 --exclude=__pycache__
	@echo "Running mypy type checker..."
	$(MYPY) ingest/ core/ alerts/

# Run tests
test:
	@echo "Running pytest..."
	$(PYTEST) tests/ -v

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