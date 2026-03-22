# STT Gateway

## What this is

A streaming Speech-to-Text gateway that accepts raw audio over a WebSocket connection, forwards it to a configurable speech provider (currently Azure Cognitive Services), and returns partial and final transcript events back to the client. Each utterance carries per-utterance latency timestamps so you can measure first-word latency, total utterance latency, and provider response delay in real time.

## Architecture

The service is built in three layers:

```
Client (WebSocket) ──→ WebSocket Route ──→ Session State ──→ Provider Abstraction
                    ←── transcript events ←──              ←── callbacks
```

**WebSocket route** (`routes/ws.py`) — Accepts the connection, dispatches incoming messages by type, and sends transcript events back to the client. Handles connection lifecycle including abrupt disconnects.

**Session state** (`models.py :: SessionState`) — Tracks per-connection state: audio byte counts, chunk counts, utterance IDs, timing timestamps, the commit flag, and a full event log. One `SessionState` instance lives for the duration of a single WebSocket session.

**Provider abstraction** (`providers/base.py :: STTProvider`) — Defines `connect`, `send_audio`, `close`, `on_partial`, and `on_final`. The Azure implementation (`providers/azure_speech.py`) wraps the Azure Speech SDK's push stream and continuous recognition, bridging its synchronous callbacks into the async event loop via `asyncio.run_coroutine_threadsafe`.

### Message flow

```
Client                          Server                         Provider
  │                               │                               │
  │── session.start ─────────────→│                               │
  │                               │── connect() ─────────────────→│
  │── audio chunk (bytes) ───────→│── send_audio() ──────────────→│
  │── audio chunk (bytes) ───────→│── send_audio() ──────────────→│
  │                               │←── on_partial("hello") ───────│
  │←── transcript.partial ────────│                               │
  │                               │←── on_partial("hello world") ─│
  │←── transcript.partial ────────│                               │
  │                               │←── on_final("hello world.") ──│
  │←── transcript.final ──────────│                               │
  │── session.end ───────────────→│                               │
  │                               │── close() ───────────────────→│
```

## Message types

### Client → Server

#### `session.start`

Initiates a new session. Must be sent before any audio.

| Field         | Type   | Description                        |
|---------------|--------|------------------------------------|
| `type`        | `"session.start"` | Literal                   |
| `session_id`  | `str`  | Client-assigned session identifier |
| `sample_rate` | `int`  | Audio sample rate (e.g. 16000)     |
| `channels`    | `int`  | Number of audio channels           |
| `encoding`    | `str`  | Audio encoding (e.g. `"pcm_s16le"`) |

#### Audio chunks

Sent as raw binary WebSocket frames. No JSON wrapper — just bytes. The server tracks sequence numbers and byte counts internally.

#### `session.end`

Signals the client is done sending audio.

| Field        | Type   | Description                        |
|--------------|--------|------------------------------------|
| `type`       | `"session.end"` | Literal                    |
| `session_id` | `str`  | Session identifier                 |

### Server → Client

#### `transcript.partial`

Intermediate transcription result. May change as more audio arrives.

| Field          | Type   | Description                         |
|----------------|--------|-------------------------------------|
| `type`         | `"transcript.partial"` | Literal              |
| `session_id`   | `str`  | Session identifier                  |
| `utterance_id` | `str`  | Utterance identifier (e.g. `"utt-1"`) |
| `text`         | `str`  | Current partial transcript text     |

#### `transcript.final`

Confirmed final transcription for a completed utterance.

| Field             | Type           | Description                                    |
|-------------------|----------------|------------------------------------------------|
| `type`            | `"transcript.final"` | Literal                                  |
| `session_id`      | `str`          | Session identifier                             |
| `utterance_id`    | `str`          | Utterance identifier                           |
| `text`            | `str`          | Final transcript text                          |
| `first_audio_ts`  | `float`        | Timestamp when first audio chunk for this utterance arrived |
| `first_partial_ts`| `float \| None`| Timestamp of the first partial for this utterance |
| `final_ts`        | `float`        | Timestamp when the final was produced          |
| `last_partial_ts` | `float \| None`| Timestamp of the last partial before this final |

#### `error`

Sent when something goes wrong.

| Field        | Type           | Description                                |
|--------------|----------------|--------------------------------------------|
| `type`       | `"error"`      | Literal                                    |
| `session_id` | `str \| None`  | Session identifier, null if no session yet |
| `code`       | `str`          | Error code: `NO_SESSION`, `PROVIDER_CONNECTION_FAILED`, `INVALID_MESSAGE` |
| `message`    | `str`          | Human-readable error message               |

## Commit strategy

The gateway tracks utterances using a **committed** flag on the session state.

- **Initial state**: `committed = True`. The session is ready for a new utterance.
- **First partial arrives**: Since `committed` is true, the gateway starts a new utterance — increments the utterance counter, assigns `utt-{n}` as the ID, records `first_audio_ts` and `first_partial_ts`, and flips `committed = False`.
- **Subsequent partials**: Update `last_partial_ts` and forward to the client. The text may change with each partial as the provider refines its hypothesis.
- **Final arrives**: The gateway records the utterance as a `CompletedUtterance`, sets `committed = True`, logs latency metrics, and sends the final event to the client. The final text is authoritative — if it differs from the last partial, the final wins.
- **Duplicate finals**: If a final arrives when `committed` is already true, it is silently dropped. This prevents double-committing if the provider fires `recognized` more than once for the same segment.
- **Partials after a final**: The next partial after a commit starts a brand-new utterance with a new ID, so stale partials from the previous segment are never misattributed.

## Latency metrics

The server logs four metrics for every committed utterance:

| Metric                     | Formula                              | What it tells you |
|----------------------------|--------------------------------------|-------------------|
| `first_word_latency`       | `first_partial_ts - first_audio_ts`  | How long after audio starts arriving before the provider returns any text. This is the metric users *feel* — it's the perceived responsiveness of the transcription. |
| `total_utterance_latency`  | `final_ts - first_audio_ts`          | End-to-end time from first audio to confirmed transcript. Useful for measuring overall pipeline throughput. |
| `utterance_duration`       | `final_ts - first_partial_ts`        | How long the provider spent refining the utterance from first partial to final. Indicates provider-side processing time. |
| `provider_response_delay`  | `final_ts - last_partial_ts`         | Gap between the last partial and the final. A large value here means the provider sat on the final after it stopped sending partials — often caused by silence detection lag. |

### Sample output

From a real run against a TEDx audio file (`data/TEDxMileHigh.wav`):

```json
{
  "utterance_count": 10,
  "first_word_latency": {
    "count": 10,
    "avg": 33.9129,
    "p50": 33.4771,
    "p95": 68.6101
  },
  "total_utterance_latency": {
    "count": 10,
    "avg": 38.6751,
    "p50": 36.2866,
    "p95": 69.3829
  },
  "provider_response_delay": {
    "count": 10,
    "avg": 0.6358,
    "p50": 0.6862,
    "p95": 1.1599
  },
  "utterance_duration": {
    "count": 10,
    "avg": 4.7622,
    "p50": 3.7458,
    "p95": 17.9429
  }
}
```

> **Note:** The `first_word_latency` and `total_utterance_latency` values in this sample are heavily inflated (30-70s) because this run used a session-scoped `first_audio_ts` — a single timestamp set when the very first audio chunk of the entire session arrived, rather than resetting per utterance. The fix is now in place (`first_audio_ts` is set from `last_chunk_ts` when a new utterance begins), but these metrics are from a prior run. The `provider_response_delay` and `utterance_duration` metrics are unaffected since they don't depend on `first_audio_ts`.

## Running it

### Start the server

```bash
# Set Azure credentials
export STT_SUBSCRIPTION_KEY="your-key"
export STT_ENDPOINT="https://eastus.api.cognitive.microsoft.com/"

# Run with uvicorn
uvicorn services.stt_gateway.main:app --host 0.0.0.0 --port 8001
```

The health endpoint is at `GET /health`.

### Run the test client

The test client streams a WAV file and prints transcript events:

```bash
# Place a WAV file at data/TEDxMileHigh.wav (or edit the path in the script)
python tmp/ws_test_server.py
```

It connects to `ws://localhost:8001/ws/audio`, streams audio in 100ms chunks, collects finals, computes latency metrics, and saves them to `data/metrics_sample.json`.

### Run tests

```bash
pytest tests/test_stt_gateway.py -v
```

Tests use fake providers (`FakeProvider`, `FailingProvider`, `EmittingProvider`) to avoid Azure dependencies. Coverage includes: happy path, audio before session start, provider connection failure, partial/final flow, abrupt disconnect, multiple utterances, and invalid JSON.

## Known limitations

- **No retry on provider disconnect.** If Azure drops the connection mid-session, the gateway does not attempt to reconnect or replay buffered audio. The session is effectively dead.
- **No timeout for missing finals.** If the provider sends partials but never sends a final (e.g. the provider hangs), the utterance stays uncommitted forever. There is no watchdog timer to force-commit or error out.
- **Single provider only.** The provider is hardcoded to `AzureSpeechProvider` in the WebSocket route. The `STTProvider` base class exists for abstraction, but there is no provider selection or factory mechanism.
- **Event log is in-memory only.** The full event log is dumped to stdout via structlog when the session ends. It is not persisted to any database or file — if the server crashes, the log is lost.
- **No authentication.** The WebSocket endpoint is open. There is no API key, JWT, or any form of client authentication.
- **Hardcoded language.** The Azure provider is hardcoded to `en-US`. There is no way for the client to specify a language at session start.
