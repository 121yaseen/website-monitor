.PHONY: format lint typecheck test check

format:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run mypy services tests

test:
	uv run pytest -v

# Run all checks in sequence (CI-friendly)
check: format lint typecheck test
