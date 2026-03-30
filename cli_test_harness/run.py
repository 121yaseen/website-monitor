#!/usr/bin/env python3
"""
CLI test harness for the agent orchestrator.

Usage:
    python -m cli_test_harness.run --session-id my-session --text "hello"

Sends a synthetic user.final_transcript event to the running orchestrator
WebSocket and prints all received events.

Set AGENT_WS_URL if the orchestrator is not on localhost:8004.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid

import websockets

AGENT_WS_URL = os.getenv("AGENT_WS_URL", "ws://localhost:8004/ws/agent")


async def run(session_id: str, text: str, barge_in_after: float | None = None) -> None:
    print(f"Connecting to {AGENT_WS_URL} ...")
    async with websockets.connect(AGENT_WS_URL) as ws:
        # Start session
        await ws.send(json.dumps({"type": "session.start", "session_id": session_id}))
        print(f"[→] session.start  session_id={session_id}")

        now = time.time()
        await ws.send(
            json.dumps(
                {
                    "type": "user.final_transcript",
                    "session_id": session_id,
                    "utterance_id": f"utt-{uuid.uuid4().hex[:6]}",
                    "text": text,
                    "first_audio_ts": now - 0.5,
                    "final_ts": now,
                }
            )
        )
        print(f"[→] user.final_transcript  text={text!r}")

        audio_chunks_received = 0
        barge_in_sent = False

        async def listen() -> None:
            nonlocal audio_chunks_received, barge_in_sent
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                except TimeoutError:
                    print("[!] Timeout waiting for response")
                    break

                if isinstance(msg, bytes):
                    audio_chunks_received += 1
                    print(f"[←] <binary audio chunk #{audio_chunks_received}  {len(msg)} bytes>")
                    # Barge-in simulation
                    if (
                        barge_in_after
                        and audio_chunks_received >= barge_in_after
                        and not barge_in_sent
                    ):
                        barge_in_sent = True
                        await ws.send(
                            json.dumps({"type": "user.barge_in", "session_id": session_id})
                        )
                        print("[→] user.barge_in")
                else:
                    data = json.loads(msg)
                    print(f"[←] {data.get('type', '?')}  {json.dumps(data, indent=2)}")
                    if data.get("type") in (
                        "assistant.audio.completed",
                        "assistant.interrupted",
                        "error",
                    ):
                        break

        await listen()

        await ws.send(json.dumps({"type": "session.end", "session_id": session_id}))
        print("[→] session.end")
        print(f"\nDone. Received {audio_chunks_received} audio chunk(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent orchestrator CLI test harness")
    parser.add_argument("--text", default="Hello, how are you?")
    parser.add_argument("--session-id", default=f"cli-{uuid.uuid4().hex[:6]}")
    parser.add_argument(
        "--barge-in-after",
        type=float,
        default=None,
        help="Send barge-in after this many audio chunks (tests interruption)",
    )
    args = parser.parse_args()

    asyncio.run(
        run(
            session_id=args.session_id,
            text=args.text,
            barge_in_after=args.barge_in_after,
        )
    )


if __name__ == "__main__":
    main()
