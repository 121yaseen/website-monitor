# 🚀 LivePulse — Real-time Service Health Monitor

> A learning project to master Python services, CI, WebSocket gateway, async/await,
> config handling, structured logging, testing, linting, formatting, and type checking.

---

## What is LivePulse?

A lightweight **uptime monitoring system** — like a mini [UptimeRobot](https://uptimerobot.com).

You configure URLs to monitor, and the system:

1. **Pings them** periodically using async HTTP calls
2. **Stores results** (status, latency, timestamp) in SQLite
3. **Pushes live status updates** to a browser dashboard via WebSocket

When you're done, you'll have a real tool you can use to monitor your own projects.

---

## Architecture

```
                    ┌──────────────┐
                    │  Target URLs │
                    │  (websites)  │
                    └──────┬───────┘
                           │ HTTP checks
                           │ every 30s
                    ┌──────▼───────┐
                    │ Probe Service│ port 8001
                    │  (async)     │
                    └──┬───────┬───┘
                       │       │
            stores     │       │ publishes events
            results    │       │
                    ┌──▼──┐ ┌──▼──────────┐
                    │ DB  │ │ WS Gateway  │ port 8003
                    │SQLite│ │             │
                    └──▲──┘ └──┬──────────┘
                       │       │ pushes live
            reads      │       │ status
                    ┌──┴──┐ ┌──▼──────────┐
                    │ API │ │    Web       │
                    │Svc  │ │  Dashboard  │
                    │     │ │ (HTML + JS) │
                    └─────┘ └─────────────┘
                   port 8002
```

**3 Python services + 1 web dashboard:**

| Component         | Port | Role                                                           |
| ----------------- | ---- | -------------------------------------------------------------- |
| **Probe Service** | 8001 | Background async loop that pings URLs, stores results          |
| **API Service**   | 8002 | REST API to manage monitors (add/list/delete) and view history |
| **WS Gateway**    | 8003 | Accepts WebSocket connections, broadcasts live probe results   |
| **Web Dashboard** | —    | Single HTML page showing live status cards                     |

---

## Learning Goals → Project Mapping

Every concept you want to learn maps to a **real, natural need** in this project:

### 1. Python Services

Three distinct services, each with its own `main.py`, config, and routes:

- `services/probe-service/` — background worker that checks URLs
- `services/api-service/` — REST API for CRUD operations
- `ws-gateway/` — WebSocket relay server

### 2. Async / Await

The probe service uses `httpx.AsyncClient` to check multiple URLs **concurrently**:

```python
async def probe_targets(targets: list[ProbeTarget]) -> list[ProbeResult]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [probe_single(client, target) for target in targets]
        return await asyncio.gather(*tasks, return_exceptions=True)

async def probe_single(client: httpx.AsyncClient, target: ProbeTarget) -> ProbeResult:
    start = time.monotonic()
    try:
        response = await client.get(target.url)
        latency_ms = (time.monotonic() - start) * 1000
        return ProbeResult(url=target.url, status=response.status_code, latency_ms=latency_ms, is_up=True)
    except httpx.RequestError:
        return ProbeResult(url=target.url, status=0, latency_ms=0, is_up=False)
```

### 3. WebSocket Gateway

The WS gateway manages browser connections and broadcasts events:

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()  # keepalive pings
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### 4. Startup Flow

Each service uses FastAPI's `lifespan` context manager:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # === STARTUP ===
    logger.info("starting_up", service="probe-service")
    await init_database()                    # create tables if needed
    app.state.http_client = httpx.AsyncClient()  # warm up HTTP pool
    probe_task = asyncio.create_task(run_probe_loop())  # start background loop
    
    yield  # app is running
    
    # === SHUTDOWN ===
    probe_task.cancel()                      # stop background loop
    await app.state.http_client.aclose()     # close HTTP pool
    logger.info("shutdown_complete")

app = FastAPI(lifespan=lifespan)
```

### 5. Config Handling

Each service uses `pydantic-settings` for type-safe configuration:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROBE_")

    # Service
    app_name: str = "probe-service"
    debug: bool = False
    port: int = 8001

    # Probing
    probe_interval_seconds: int = 30
    probe_timeout_seconds: int = 10

    # Database
    database_url: str = "sqlite+aiosqlite:///./livepulse.db"

    # Gateway
    ws_gateway_url: str = "ws://localhost:8003/ws/internal"

settings = Settings()
```

`.env` file:
```env
PROBE_DEBUG=true
PROBE_PROBE_INTERVAL_SECONDS=10
PROBE_DATABASE_URL=sqlite+aiosqlite:///./dev.db
```

### 6. Structured Logging

Using `structlog` for JSON logs in production, pretty logs in development:

```python
import structlog

def setup_logging(debug: bool = False):
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if debug:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(processors=processors)

# Usage:
logger = structlog.get_logger()
logger.info("probe_complete", url="https://google.com", status=200, latency_ms=45)

# Dev output:
# 2026-03-08T16:50:00 [info] probe_complete  url=https://google.com status=200 latency_ms=45

# Prod output (JSON):
# {"event":"probe_complete","url":"https://google.com","status":200,"latency_ms":45,"level":"info","timestamp":"2026-03-08T16:50:00"}
```

### 7. Formatter (Ruff Format)

Configured in `pyproject.toml`:

```toml
[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "auto"
```

Run: `ruff format .`

### 8. Linter (Ruff Check)

Configured in `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH"]
ignore = []
```

Run: `ruff check .`

### 9. Type Checking (mypy)

Configured in `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
```

Run: `mypy services/ ws-gateway/`

### 10. Unit Tests

Test individual components in isolation using `pytest` + `pytest-asyncio`:

```python
# tests/unit/test_prober.py
import pytest
from unittest.mock import AsyncMock, patch
from services.probe_service.prober import probe_single

@pytest.mark.asyncio
async def test_probe_success():
    mock_response = AsyncMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    target = ProbeTarget(id="1", url="https://example.com")
    result = await probe_single(mock_client, target)

    assert result.is_up is True
    assert result.status == 200
    assert result.latency_ms > 0


@pytest.mark.asyncio
async def test_probe_timeout():
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ReadTimeout("timeout")

    target = ProbeTarget(id="1", url="https://slow-site.com")
    result = await probe_single(mock_client, target)

    assert result.is_up is False
```

```python
# tests/unit/test_config.py
def test_default_config():
    settings = Settings()
    assert settings.probe_interval_seconds == 30
    assert settings.debug is False

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("PROBE_DEBUG", "true")
    monkeypatch.setenv("PROBE_PROBE_INTERVAL_SECONDS", "5")
    settings = Settings()
    assert settings.debug is True
    assert settings.probe_interval_seconds == 5
```

### 11. Smoke Tests

Verify services are alive and can communicate:

```python
# tests/smoke/test_health.py
import pytest
import httpx

SERVICES = [
    ("probe-service", "http://localhost:8001/health"),
    ("api-service", "http://localhost:8002/health"),
    ("ws-gateway", "http://localhost:8003/health"),
]

@pytest.mark.parametrize("name,url", SERVICES)
def test_service_health(name, url):
    response = httpx.get(url, timeout=5.0)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

```python
# tests/smoke/test_ws_connect.py
import pytest
import websockets

@pytest.mark.asyncio
async def test_ws_gateway_accepts_connection():
    async with websockets.connect("ws://localhost:8003/ws") as ws:
        assert ws.open
```

### 12. CI (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: mypy services/ ws-gateway/

  test-unit:
    runs-on: ubuntu-latest
    needs: [lint, type-check]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ -v --tb=short

  test-smoke:
    runs-on: ubuntu-latest
    needs: [test-unit]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: |
          # Start services in background
          python -m uvicorn services.api_service.main:app --port 8002 &
          python -m uvicorn ws_gateway.main:app --port 8003 &
          sleep 3
      - run: pytest tests/smoke/ -v --tb=short
```

---

## Project Structure

```
python/
├── .github/workflows/
│   └── ci.yml
├── .editorconfig
├── .gitignore
├── pyproject.toml                  # deps + ruff + mypy + pytest config
├── Makefile                        # convenience commands
├── README.md
│
├── services/
│   ├── probe_service/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI app + lifespan + background probe loop
│   │   ├── config.py              # pydantic-settings
│   │   ├── logger.py              # structlog setup
│   │   ├── prober.py              # core async probing logic
│   │   ├── db.py                  # aiosqlite database operations
│   │   ├── publisher.py           # publishes events to WS gateway
│   │   ├── models.py              # ProbeResult, ProbeTarget schemas
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── health.py
│   │
│   └── api_service/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── logger.py
│       ├── db.py
│       ├── models.py              # Monitor, MonitorCreate, ProbeHistory
│       └── routes/
│           ├── __init__.py
│           ├── health.py
│           └── monitors.py        # CRUD endpoints
│
├── ws_gateway/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── logger.py
│   ├── manager.py                 # ConnectionManager
│   ├── models.py                  # WebSocket event schemas
│   └── routes/
│       ├── __init__.py
│       ├── health.py
│       └── ws.py                  # WebSocket endpoint
│
├── web/
│   ├── index.html                 # dashboard UI
│   ├── style.css
│   └── app.js                     # WS connection + API calls
│
├── tests/
│   ├── conftest.py                # shared fixtures (test DB, async client)
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_prober.py         # mock HTTP → test probe logic
│   │   ├── test_config.py         # test config validation + defaults
│   │   ├── test_models.py         # test schema validation
│   │   └── test_monitors_api.py   # test CRUD routes
│   └── smoke/
│       ├── __init__.py
│       ├── test_health.py         # all services respond to /health
│       └── test_ws_connect.py     # can connect to WS gateway
│
├── scripts/
│   ├── start_all.sh               # start all services for local dev
│   └── seed_monitors.py           # add sample URLs to monitor
│
└── docs/
    ├── project-plan.md            # ← this file
    ├── architecture.md
    └── decisions/
        └── 001-tech-stack.md
```

---

## Makefile

```makefile
.PHONY: install lint format type-check test test-unit test-smoke dev

install:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

type-check:
	mypy services/ ws_gateway/

test: test-unit

test-unit:
	pytest tests/unit/ -v

test-smoke:
	pytest tests/smoke/ -v

dev-probe:
	uvicorn services.probe_service.main:app --reload --port 8001

dev-api:
	uvicorn services.api_service.main:app --reload --port 8002

dev-gateway:
	uvicorn ws_gateway.main:app --reload --port 8003

dev:
	sh scripts/start_all.sh
```

---

## Dependencies

```toml
# pyproject.toml
[project]
name = "livepulse"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "httpx>=0.28.0",
    "aiosqlite>=0.21.0",
    "pydantic-settings>=2.7.0",
    "structlog>=24.4.0",
    "websockets>=14.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.25.0",
    "mypy>=1.14.0",
    "ruff>=0.9.0",
    "httpx",  # for test client
]
```

---

## Build Order

### Phase 1: Foundation (Day 1)
- [ ] Fill `.gitignore`, `.editorconfig`, `pyproject.toml`
- [ ] Set up `Makefile`
- [ ] Create `api-service` with `/health` endpoint, config, logger
- [ ] Write first unit test + smoke test
- [ ] Run `make lint && make type-check && make test` — all green ✅

### Phase 2: CRUD API (Day 2)
- [ ] Add SQLite DB setup in `api-service` (startup flow)
- [ ] Build `POST/GET/DELETE /monitors` routes
- [ ] Write unit tests for each route
- [ ] Structured logs for every request

### Phase 3: Probe Service (Day 3)
- [ ] Build `probe-service` with async background loop
- [ ] Use `httpx.AsyncClient` to probe URLs concurrently
- [ ] Store results in SQLite
- [ ] Unit test the probe logic with mocked HTTP

### Phase 4: WebSocket Gateway (Day 4)
- [ ] Build `ws-gateway` with connection manager
- [ ] Probe service publishes results → gateway broadcasts
- [ ] Unit test WS message handling
- [ ] Smoke test: connect + receive a message

### Phase 5: Dashboard + CI (Day 5)
- [ ] Build web dashboard (HTML + vanilla JS)
- [ ] Set up `.github/workflows/ci.yml`
- [ ] Push to GitHub → watch CI go green 🟢
- [ ] Write `scripts/start_all.sh`

---

## What the Dashboard Looks Like

```
┌─────────────────────────────────────────────────┐
│  ⚡ LivePulse                           [+ Add] │
├─────────────────────────────────────────────────┤
│                                                 │
│  🟢  api.example.com       45ms     2s ago      │
│  🟢  google.com            12ms     2s ago      │
│  🔴  broken-site.test     timeout   2s ago      │
│  🟢  github.com            89ms     2s ago      │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## Tech Stack Summary

| Concern       | Tool                          | Why                                            |
| ------------- | ----------------------------- | ---------------------------------------------- |
| Web Framework | **FastAPI**                   | Async-native, WebSocket support, built-in docs |
| Formatter     | **Ruff** (`ruff format`)      | Replaces Black + isort, Rust-fast              |
| Linter        | **Ruff** (`ruff check`)       | Replaces flake8 + pylint, 100x faster          |
| Type Checker  | **mypy**                      | Industry standard, strict mode                 |
| Tests         | **pytest** + `pytest-asyncio` | De-facto standard, great async support         |
| Config        | **pydantic-settings**         | Type-safe `.env` loading + validation          |
| Logging       | **structlog**                 | JSON in prod, pretty in dev                    |
| Database      | **aiosqlite**                 | Async SQLite, zero setup                       |
| HTTP Client   | **httpx**                     | Async HTTP, used for probing + tests           |
| CI            | **GitHub Actions**            | Free, integrates with repo                     |
