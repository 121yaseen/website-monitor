import asyncio
import json
import websockets

async def test():
    async with websockets.connect("ws://localhost:8001/ws/audio") as ws:
        # 1. Send session.start
        await ws.send(json.dumps({
            "type": "session.start",
            "session_id": "test-001",
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm_s16le"
        }))
        print("Sent session.start")

        # 2. Send 5 fake audio chunks (binary)
        for i in range(5):
            fake_audio = b"\x00" * 3200  # 100ms of 16kHz 16-bit mono
            await ws.send(fake_audio)
            print(f"Sent chunk {i+1}, size={len(fake_audio)}")

        # 3. Send session.end
        await ws.send(json.dumps({
            "type": "session.end",
            "session_id": "test-001"
        }))
        print("Sent session.end")

asyncio.run(test())
