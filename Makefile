.PHONY: setup format lint check-types test security ci clean

setup:
	@if [ -f .env.example ] && [ ! -f .env ]; then cp .env.example .env; fi
	uv sync

format:
	uv run ruff check --fix .
	uv run ruff format .

lint:
	uv run ruff check .
	uv run ruff format --check .

check-types:
	uv run mypy .

test:
	uv run pytest

security:
	uv run bandit -c pyproject.toml -r . -ll
	uv run pip-audit

ci: lint check-types security test

clean:
	rm -rf .venv/ build/ dist/ .mypy_cache/ .ruff_cache/ .pytest_cache/
