import asyncio
import json
import os
import statistics
from datetime import UTC, datetime

import websockets

from services.ws_gateway.models import EchoRequest, EchoResponse


async def main() -> None:
    latencies_ms: list[float] = []

    if not os.path.exists("data"):
        os.makedirs("data")

    if not os.path.exists("data/latency_samples.jsonl"):
        with open("data/latency_samples.jsonl", "w") as f:
            f.write("")

    for i in range(10):
        async with websockets.connect("ws://localhost:8000/ws/echo") as ws:
            sent_at = datetime.now(UTC)
            msg = EchoRequest(message="hello", client_sent_at=sent_at).model_dump_json()

            await ws.send(msg)
            response = EchoResponse.model_validate_json(await ws.recv())
            received_at = datetime.now(UTC)

            latency_ms = (received_at - sent_at).total_seconds() * 1000
            latencies_ms.append(latency_ms)

            server_processing_ms = (
                response.server_sent_at - response.server_received_at
            ).total_seconds() * 1000

            with open("data/latency_samples.jsonl", "a") as f:
                f.write(
                    json.dumps(
                        {
                            "session_id": response.session_id,
                            "message_index": i,
                            "client_sent_at": sent_at.isoformat(),
                            "server_received_at": response.server_received_at.isoformat(),
                            "server_sent_at": response.server_sent_at.isoformat(),
                            "client_received_at": received_at.isoformat(),
                            "latency_ms": latency_ms,
                            "server_processing_ms": server_processing_ms,
                        }
                    )
                    + "\n"
                )

        await asyncio.sleep(1)

    # summary after all samples are collected
    p95 = (
        statistics.quantiles(latencies_ms, n=100)[94] if len(latencies_ms) >= 2 else latencies_ms[0]
    )

    with open("data/latency_samples.jsonl", "a") as f:
        f.write(
            json.dumps(
                {
                    "summary": {
                        "count": len(latencies_ms),
                        "min_ms": min(latencies_ms),
                        "max_ms": max(latencies_ms),
                        "avg_ms": statistics.mean(latencies_ms),
                        "p50_ms": statistics.median(latencies_ms),
                        "p95_ms": p95,
                    }
                }
            )
            + "\n"
        )


if __name__ == "__main__":
    asyncio.run(main())
