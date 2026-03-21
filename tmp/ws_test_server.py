import asyncio
import json
import wave

import websockets


async def test():
    uri = "ws://localhost:8001/ws/audio"

    # Read the WAV file
    with wave.open("data/harvard.wav", "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        pcm_data = wf.readframes(wf.getnframes())
        print(f"Audio: {sample_rate}Hz, {channels}ch, {len(pcm_data)} bytes")

    async with websockets.connect(uri) as ws:
        # Background listener
        async def listen():
            try:
                async for msg in ws:
                    data = json.loads(msg)
                    print(f"← {data['type']}: {data.get('text', data)}")
            except websockets.ConnectionClosed:
                pass

        listener = asyncio.create_task(listen())

        # Send session.start with actual audio params
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

        # Send PCM data in chunks (100ms worth of audio each)
        chunk_size = sample_rate * channels * 2 // 10  # 2 bytes per sample, 10 chunks/sec
        for i in range(0, len(pcm_data), chunk_size):
            chunk = pcm_data[i : i + chunk_size]
            await ws.send(chunk)
            print(f"→ Sent chunk {i // chunk_size + 1}, size={len(chunk)}")
            await asyncio.sleep(0.1)  # real-time pacing

        # Send session.end
        await ws.send(json.dumps({"type": "session.end", "session_id": "test-001"}))
        print("→ Sent session.end")

        # Wait for final transcripts
        await asyncio.sleep(3)
        listener.cancel()


asyncio.run(test())
