.PHONY: format lint typecheck test check run-api run-ws run-probe

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

# Run services individually
run-api:
	uv run uvicorn services.api_service.main:app --port 8001 --reload

run-ws:
	uv run uvicorn services.ws_gateway.main:app --port 8000 --reload

run-probe:
	uv run uvicorn services.probe_service.main:app --port 8003 --reload
