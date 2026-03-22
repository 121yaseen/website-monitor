import asyncio
import json
import statistics
import wave

import websockets

utterances = []


def compute_metrics(utterances: list[dict]) -> dict:
    """Compute latency metrics with count, avg, p50, p95 from final events."""
    if not utterances:
        return {}

    first_word_latencies = []
    total_latencies = []
    provider_delays = []
    utterance_durations = []
    for u in utterances:
        first_audio = u["first_audio_ts"]
        first_partial = u.get("first_partial_ts")
        final = u["final_ts"]
        last_partial = u.get("last_partial_ts")
        utterance_duration = final - first_partial

        if first_partial and first_audio:
            first_word_latencies.append(first_partial - first_audio)
        if first_audio:
            total_latencies.append(final - first_audio)
        if last_partial:
            provider_delays.append(final - last_partial)
        if utterance_duration:
            utterance_durations.append(utterance_duration)

    def summarize(values: list[float]) -> dict:
        if not values:
            return {"count": 0}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "count": n,
            "avg": round(statistics.mean(sorted_vals), 4),
            "p50": round(statistics.median(sorted_vals), 4),
            "p95": round(sorted_vals[min(int(0.95 * n), n - 1)], 4),
        }

    return {
        "utterance_count": len(utterances),
        "first_word_latency": summarize(first_word_latencies),
        "total_utterance_latency": summarize(total_latencies),
        "provider_response_delay": summarize(provider_delays),
        "utterance_duration": summarize(utterance_durations),
    }


async def test():
    uri = "ws://localhost:8001/ws/audio"
    with wave.open("data/TEDxMileHigh.wav", "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        pcm_data = wf.readframes(wf.getnframes())
        print(f"Audio: {sample_rate}Hz, {channels}ch, {len(pcm_data)} bytes")

    async with websockets.connect(uri) as ws:

        async def listen():
            try:
                async for msg in ws:
                    data = json.loads(msg)
                    print(f"← {data['type']}: {data.get('text', data)}")
                    if data["type"] == "transcript.final":
                        utterances.append(data)
            except websockets.ConnectionClosed:
                pass

        listener = asyncio.create_task(listen())

        await ws.send(
            json.dumps(
                {
                    "type": "session.start",
                    "session_id": "test-001",
                    "sample_rate": sample_rate,
                    "channels": channels,
                    "encoding": "pcm_s16le",
                }
            )
        )
        print("→ Sent session.start")

        chunk_size = sample_rate * channels * 2 // 10
        for i in range(0, len(pcm_data), chunk_size):
            chunk = pcm_data[i : i + chunk_size]
            await ws.send(chunk)
            print(f"→ Sent chunk {i // chunk_size + 1}, size={len(chunk)}")
            await asyncio.sleep(0.1)

        await ws.send(json.dumps({"type": "session.end", "session_id": "test-001"}))
        print("→ Sent session.end")

        await asyncio.sleep(3)
        listener.cancel()


for i in range(1):
    try:
        print(f"\n{'=' * 60}\nRUN {i + 1}\n{'=' * 60}")
        asyncio.run(test())
    except Exception as e:
        print(f"Run {i + 1} failed: {e}")

# Compute and display metrics
metrics = compute_metrics(utterances)
print("\n" + "=" * 60)
print("LATENCY METRICS SUMMARY")
print("=" * 60)
print(json.dumps(metrics, indent=2))

# Save to file
with open("data/metrics_sample.json", "w") as f:
    json.dump(metrics, f, indent=2)
print("\nMetrics saved to data/metrics_sample.json")
