import structlog
import asyncio

from services.probe_service.logger import configure_logging
from services.probe_service.models import ProbeRequest
from services.probe_service.prober import probe


configure_logging()

logger = structlog.get_logger("probe_service")

async def main():
    logger.info("service_started", port=8000, env="dev")
    logger.warning("cache_miss", key="user:123")

    request = ProbeRequest(
        target_url="https://www.hinoun.com/",
        timeout_in_seconds=10
    )

    logger.info("probe_request", request=request)

    result = await probe(request)

    logger.info("probe_result", success=result.success, response=result.response)

asyncio.run(main())