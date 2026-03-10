from datetime import datetime

import httpx

from services.probe_service.models import ProbeRequest, ProbeResponse, ProbeResult


async def probe(request: ProbeRequest) -> ProbeResult:

    obj = ProbeResult(
        probe_id=str(request.request_id), request=request, success=False, response=None
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(str(request.target_url), timeout=request.timeout_in_seconds)
            response.raise_for_status()
            obj.response = ProbeResponse(
                target_url=request.target_url,
                status_code=response.status_code,
                status="healthy",
                latency=response.elapsed.total_seconds(),
                error=None,
                timestamp=datetime.now(),
            )
            obj.success = True
    except httpx.HTTPStatusError as e:
        obj.response = ProbeResponse(
            target_url=request.target_url,
            status_code=e.response.status_code,
            status="unhealthy",
            latency=e.response.elapsed.total_seconds(),
            error=str(e),
            timestamp=datetime.now(),
        )
    except Exception as e:
        obj.response = ProbeResponse(
            target_url=request.target_url,
            status_code=None,
            status="unhealthy",
            latency=0,
            error=str(e),
            timestamp=datetime.now(),
        )
    return obj
