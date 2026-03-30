# Voice AI Systems Lab

A week-by-week learning project building production-grade voice AI infrastructure from scratch — from a basic probe service to a full duplex voice agent with real-time speech synthesis and barge-in.

---

## What This Is

This repo is a structured 3-week engineering lab for transitioning from backend development into Voice AI. Each week layers on top of the previous one:

| Week | Focus | Key Output |
|------|-------|-----------|
| 1 | Foundations — FastAPI, async, WebSockets | Probe service, WS gateway |
| 2 | Speech-to-Text — Azure STT, streaming audio | STT gateway with partial/final transcripts |
| 3 | Duplex Voice Agent — LLM + TTS + barge-in | Full voice loop with latency metrics |

---

## Architecture (Week 3)

```
Client / Test harness
   │  WebSocket (binary audio + JSON control)
   ▼
STT Gateway  :8002
   │  transcript.partial / transcript.final
   ▼
Agent Orchestrator  :8004   ◄── Week 3 (new)
   ├──► Azure OpenAI (gpt-4.1-mini)   LLM adapter
   └──► Azure TTS (Ava Multilingual)  TTS adapter
        │  streamed MP3 audio chunks
        ▼
   Client receives spoken assistant response
```

The architecture is **cascaded** (STT → LLM → TTS as three separate API calls) rather than fused, prioritising observability, vendor flexibility, and debuggability over raw latency. See [`docs/cascaded_agent_loop.md`](docs/cascaded_agent_loop.md) for the full design rationale.

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| `probe_service` | 8003 | HTTP health prober with SQLite persistence |
| `ws_gateway` | 8000 | WebSocket echo gateway (Week 1 foundation) |
| `stt_gateway` | 8002 | Streaming STT via Azure Cognitive Services |
| `agent_orchestrator` | 8004 | Duplex voice agent control plane |

---

## Project Structure

```
voice-systems-lab/
├── services/
│   ├── probe_service/          # Week 1 – HTTP prober
│   ├── ws_gateway/             # Week 1 – WS echo gateway
│   ├── stt_gateway/            # Week 2 – Azure STT streaming
│   │   ├── providers/
│   │   │   ├── base.py         # STTProvider ABC
│   │   │   └── azure_speech.py # Azure Continuous Recognition
│   │   └── routes/ws.py        # /ws/audio endpoint
│   └── agent_orchestrator/     # Week 3 – voice agent
│       ├── adapters/
│       │   ├── llm_base.py     # LLMAdapter ABC
│       │   ├── tts_base.py     # TTSAdapter ABC
│       │   ├── openai_llm.py   # Azure OpenAI implementation
│       │   ├── azure_tts.py    # Azure TTS implementation
│       │   └── stub.py         # Stub adapters (no API keys needed)
│       ├── orchestrator.py     # Core state machine + pipeline
│       ├── metrics.py          # p50/p95 latency collector
│       ├── models.py           # Typed event schema + domain models
│       ├── config.py           # Settings (AGENT_ env prefix)
│       └── routes/
│           ├── ws.py           # /ws/agent WebSocket endpoint
│           ├── health.py       # GET /health
│           └── metrics.py      # GET /metrics
├── cli_test_harness/
│   └── run.py                  # CLI client for manual testing
├── scripts/
│   └── summarize_metrics.py    # Print p50/p95 latency table
├── docs/
│   ├── ARCHITECTURE.md         # Full system design
│   ├── STATE_MACHINE.md        # Session state machine spec
│   ├── cascaded_agent_loop.md  # Why cascaded vs fused
│   └── week3_latency_report.md # Latency measurements & analysis
└── tests/
    ├── test_agent_orchestrator.py  # 28 tests for Week 3
    ├── test_stt_gateway.py
    └── ...
```

---

## Setup

### Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (package manager)

### Install dependencies

```bash
uv sync
```

### Configure environment

Copy the example and fill in your keys:

```bash
cp .env.example .env   # or edit .env directly
```

Required variables:

```env
# Azure STT (Cognitive Services Speech)
STT_SUBSCRIPTION_KEY=<your-speech-key>
STT_ENDPOINT=https://<region>.api.cognitive.microsoft.com/

# Agent Orchestrator — LLM (Azure OpenAI)
AGENT_OPENAI_API_KEY=<your-azure-openai-key>
AGENT_OPENAI_BASE_URL=https://<resource>.openai.azure.com/openai/v1
AGENT_OPENAI_MODEL=gpt-4.1-mini
AGENT_LLM_IS_AZURE=true

# Agent Orchestrator — TTS (Azure Cognitive Services Speech)
# NOTE: This is the Speech key, NOT the OpenAI key
AGENT_AZURE_TTS_KEY=<your-speech-key>
AGENT_AZURE_TTS_REGION=eastus
AGENT_AZURE_TTS_VOICE=en-US-AvaMultilingualNeural
```

> **If you leave `AGENT_OPENAI_API_KEY` or `AGENT_AZURE_TTS_KEY` blank**, the orchestrator automatically falls back to stub adapters — it still runs the full pipeline with a hardcoded LLM response and silent audio, which is useful for testing the event flow without live credentials.

---

## Running Services

```bash
# STT gateway (port 8002)
make run-stt

# Agent orchestrator (port 8004) — hot-reload enabled
make run-agent

# Other services
make run-api      # port 8001
make run-probe    # port 8003
```

---

## Testing

### Unit / integration tests

```bash
make test          # runs all 92 tests
uv run pytest tests/test_agent_orchestrator.py -v   # Week 3 only (28 tests)
```

### CLI test harness

Send a synthetic turn to the running orchestrator and see all events:

```bash
# Normal turn
make harness TEXT="what is the capital of France?"

# Barge-in simulation — interrupts assistant after 2 audio chunks
uv run python -m cli_test_harness.run \
  --text "tell me a long story" \
  --barge-in-after 2
```

Example output (normal turn):

```
[→] session.start
[→] user.final_transcript  text='what is the capital of France?'
[←] assistant.response.started
[←] assistant.response.text   "The capital of France is Paris."
[←] assistant.audio.chunk  seq=0  (4096 bytes)
...
[←] assistant.audio.completed  latency_summary={...}
[→] session.end

Done. Received 10 audio chunk(s).
```

Example output (barge-in):

```
[→] user.barge_in
[←] assistant.interrupted  {"type": "assistant.interrupted", ...}

Done. Received 2 audio chunk(s).
```

---

## Latency Metrics

The orchestrator captures 7 timestamps per completed turn and exposes p50/p95 summaries at `GET /metrics`.

### Viewing metrics

```bash
# Live (requires running agent)
python scripts/summarize_metrics.py --url http://localhost:8004/metrics

# From a JSON dump
python scripts/summarize_metrics.py --file metrics_dump.json
```

### Measured results (Azure East US, `gpt-4.1-mini`)

Measured over completed turns via the CLI harness. STT latency is synthetic (0.5 s hardcoded offset from the harness) since there is no real microphone input in this test — real microphone input produces ~300–400 ms STT latency.

```
Stage                             p50 (s)    p95 (s)    Count
--------------------------------------------------------------
stt_latency                         0.500      0.500        2  ← synthetic
llm_latency                         4.448      6.859        2
tts_startup_latency                 0.951      1.037        2
total_response_latency              5.401      7.898        2
total_turn_duration                 6.404      8.893        2
```

### Latency breakdown per stage

```
user_first_audio_ts     ──────────────────────── t=0.000
user_final_transcript_ts ───────────────────── t≈0.380   [STT: ~380 ms real / 500 ms synthetic]
llm_request_ts          ───────────────────── t≈0.381
llm_response_ts         ─────────────────────── t≈2.300  [LLM: ~1.4–7 s  ← biggest bottleneck]
tts_request_ts          ─────────────────────── t≈2.301
tts_first_chunk_ts      ───────────────────── t≈3.300    [TTS startup: ~0.85–1.1 s]
tts_completed_ts        ───────────────────── t≈4.200    [TTS stream: ~0.9–1.6 s]

Total response latency (transcript → first audio):  ~2.5–8.2 s
Total turn duration:                                ~3.6–9.2 s
```

### Bottleneck analysis

| Stage | Share of TTFA | Notes |
|---|---|---|
| **LLM latency** | ~75% | Largest bottleneck. Azure OpenAI throttling causes spikes up to 7 s on cold requests. Warm requests settle around 1.4–1.9 s. |
| TTS startup | ~20% | Azure REST synthesis: ~0.85–1.1 s to first MP3 byte. WebSocket SDK endpoint can reduce this to <100 ms. |
| STT latency | ~5% | Azure adds ~150–400 ms after speech ends before emitting `final`. |

### Optimisation roadmap (Week 4)

1. **Sentence-streaming TTS** — Buffer LLM tokens into sentences, start TTS on sentence 1 while LLM continues. Target TTFA <1 s.
2. **Azure TTS WebSocket SDK** — Replace REST endpoint with streaming SDK; cuts TTS startup by ~70%.
3. **LLM connection warm-up** — Keep a persistent HTTP connection to Azure OpenAI to avoid cold-start penalties.
4. **Partial-triggered LLM** — Speculatively call LLM on high-confidence STT partials to overlap STT tail with LLM prefill.

---

## Event Protocol

### Client → Orchestrator

```jsonc
// Start a session
{ "type": "session.start", "session_id": "my-session", "system_prompt": "..." }

// Send a finalised user utterance (normally emitted by STT gateway)
{ "type": "user.final_transcript", "session_id": "...", "utterance_id": "utt-1",
  "text": "hello", "first_audio_ts": 1234.56, "final_ts": 1234.89 }

// Signal user started speaking during assistant playback
{ "type": "user.barge_in", "session_id": "..." }

// End session
{ "type": "session.end", "session_id": "..." }
```

### Orchestrator → Client

```jsonc
{ "type": "assistant.response.started", "session_id": "...", "turn_id": "..." }
{ "type": "assistant.response.text",    "session_id": "...", "turn_id": "...", "text": "..." }
{ "type": "assistant.audio.chunk",      "session_id": "...", "turn_id": "...", "seq": 0 }
<binary frame: raw MP3 audio chunk>
{ "type": "assistant.audio.completed",  "session_id": "...", "turn_id": "...",
  "latency_summary": { "llm_latency": 1.43, "tts_startup_latency": 0.95, ... } }
{ "type": "assistant.interrupted",      "session_id": "...", "turn_id": "..." }
{ "type": "error",                      "code": "...", "message": "..." }
```

---

## Session State Machine

```
idle → listening → transcribing → thinking → speaking → listening
                                                  │
                                           (barge-in detected)
                                                  ▼
                                            interrupted → listening
```

Full spec: [`docs/STATE_MACHINE.md`](docs/STATE_MACHINE.md)

---

## Code Quality

```bash
make format      # ruff format
make lint        # ruff check
make typecheck   # mypy --strict
make check       # all of the above + tests
```

---

## Conversation Memory

The orchestrator maintains a rolling window of the last 8 turns (configurable via `AGENT_MAX_CONTEXT_TURNS`) per session. Interrupted turns are kept in history with `interrupted=True` so the LLM has full context for the next response.

---

## Known Limitations

- **No real-time microphone input** — the CLI harness sends synthetic transcript events. Full duplex requires connecting the STT gateway output to the orchestrator input (Week 4).
- **Metrics are in-process only** — the `MetricsCollector` resets on server restart. Persistent metrics storage (e.g., to a file or SQLite) is a follow-up.
- **TTS is REST-based** — the Azure REST synthesis endpoint buffers the full audio before streaming. Switching to the Azure Speech SDK WebSocket endpoint will cut TTS startup latency significantly.
- **No VAD** — barge-in detection is client-driven (`user.barge_in` message). Production systems need server-side VAD to detect speech onset reliably.
