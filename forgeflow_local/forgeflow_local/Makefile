.PHONY: help install install-dev test test-cov lint format typecheck clean build docs

PYTHON := python3
PIP := pip

help:
	@echo "ForgeFlow Development Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install      Install production dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo "  test         Run tests"
	@echo "  test-cov     Run tests with coverage"
	@echo "  lint         Run linters (flake8, black check, isort check)"
	@echo "  format       Format code with black and isort"
	@echo "  typecheck    Run mypy type checking"
	@echo "  clean        Remove build artifacts"
	@echo "  build        Build distribution packages"
	@echo "  docs         Generate documentation"
	@echo "  doctor       Run ForgeFlow health check"

install:
	$(PIP) install -r requirements.txt

install-dev: install
	$(PIP) install -e ".[dev]"
	pre-commit install

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=agents --cov=core --cov=cli --cov-report=html --cov-report=term

lint:
	flake8 agents/ core/ cli/ mcp_servers/
	black --check --line-length=100 agents/ core/ cli/
	isort --check-only agents/ core/ cli/

format:
	black --line-length=100 agents/ core/ cli/
	isort --profile=black --line-length=100 agents/ core/ cli/

typecheck:
	mypy agents/ core/ cli/ --ignore-missing-imports

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build: clean
	$(PYTHON) -m build

docs:
	@echo "Documentation is in docs/ directory"

doctor:
	$(PYTHON) -m cli.forgeflow doctor
