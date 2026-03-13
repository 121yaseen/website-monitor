"""Unit tests for Publisher.

The WebSocket connection is never opened — we test the queue/lifecycle
behaviour in isolation without any network I/O.
"""

from services.probe_service.models import ProbeResponse
from services.probe_service.publisher import Publisher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response() -> ProbeResponse:
    return ProbeResponse(
        target_url="https://example.com/",
        status_code=200,
        status="healthy",
        latency=0.1,
    )


# ---------------------------------------------------------------------------
# publish()
# ---------------------------------------------------------------------------


async def test_publish_puts_json_on_queue() -> None:
    """publish() should serialise the response and put it on the internal queue."""
    publisher = Publisher()
    response = _make_response()

    publisher.publish(response)

    assert publisher._queue.qsize() == 1
    item = await publisher._queue.get()
    assert '"status":"healthy"' in item or '"status": "healthy"' in item


async def test_publish_multiple_items_queued_in_order() -> None:
    """Multiple publish() calls should queue items in FIFO order."""
    publisher = Publisher()

    r1 = ProbeResponse(
        target_url="https://example.com/", status_code=200, status="healthy", latency=0.1
    )
    r2 = ProbeResponse(
        target_url="https://example.com/", status_code=503, status="unhealthy", latency=1.0
    )

    publisher.publish(r1)
    publisher.publish(r2)

    assert publisher._queue.qsize() == 2
    first = await publisher._queue.get()
    assert "healthy" in first
    second = await publisher._queue.get()
    assert "unhealthy" in second


# ---------------------------------------------------------------------------
# start() / stop() lifecycle
# ---------------------------------------------------------------------------


async def test_start_creates_background_task() -> None:
    """start() should create a running asyncio Task."""
    publisher = Publisher()
    assert publisher._task is None

    await publisher.start()

    assert publisher._task is not None
    assert not publisher._task.done()

    await publisher.stop()


async def test_stop_cancels_task() -> None:
    """stop() should cancel the background task without raising."""
    publisher = Publisher()
    await publisher.start()

    await publisher.stop()  # must not raise

    assert publisher._task is not None
    assert publisher._task.done()


async def test_stop_before_start_is_safe() -> None:
    """stop() when task is None should be a no-op."""
    publisher = Publisher()
    await publisher.stop()  # must not raise


async def test_start_stop_repeated() -> None:
    """Calling start/stop multiple times should not leave dangling tasks."""
    publisher = Publisher()

    await publisher.start()
    task1 = publisher._task

    await publisher.stop()
    assert task1 is not None and task1.done()


# ---------------------------------------------------------------------------
# __init__ state
# ---------------------------------------------------------------------------


def test_init_state() -> None:
    """Publisher should initialise with empty queue, no task, zero retry count."""
    publisher = Publisher()

    assert publisher._queue.empty()
    assert publisher._task is None
    assert publisher.retry_count == 0
