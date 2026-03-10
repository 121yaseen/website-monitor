import asyncio

import structlog

from services.probe_service.config import settings
from services.probe_service.db import DBObject
from services.probe_service.logger import configure_logging
from services.probe_service.models import ProbeRequest
from services.probe_service.prober import probe

configure_logging()

logger = structlog.get_logger("probe_service")


async def main() -> None:
    logger.info("service_started", port=settings.port, env=settings.env)

    db = await DBObject.get_db_object(settings.db_connection_string)

    request = ProbeRequest(target_url="https://www.hinoun.com/", timeout_in_seconds=10)

    logger.info("probe_request", request=request)

    result = await probe(request)

    logger.info("probe_result", success=result.success, response=result.response)

    await db.save_result(result)

    results = await db.get_results(result.probe_id)
    logger.info("probe_results", results=results[0])


if __name__ == "__main__":
    asyncio.run(main())
