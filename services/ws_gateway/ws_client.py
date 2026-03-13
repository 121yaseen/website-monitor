import asyncio
from datetime import datetime

import websockets

from services.ws_gateway.models import EchoRequest


async def main() -> None:
    async with websockets.connect("ws://localhost:8000/ws/echo") as ws:
        sent_at = datetime.now()
        msg = EchoRequest(message="hello", client_sent_at=sent_at).model_dump_json()
        await ws.send(msg)
        response = await ws.recv()
        received_at = datetime.now()
        print(response)
        latency = received_at - sent_at
        print(f"Latency: {latency.total_seconds() * 1000}ms")


if __name__ == "__main__":
    asyncio.run(main())
