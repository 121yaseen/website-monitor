import asyncio

import websockets


async def handler(websocket):
    async for message in websocket:
        print(f"Received: {message}")


async def main():
    async with websockets.serve(handler, "localhost", 8000):
        print("WS server running on ws://localhost:8000")
        await asyncio.Future()  # run forever


asyncio.run(main())
