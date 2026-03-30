"""
Latency metrics collection and reporting.

Collects TurnLatencyMetrics for each completed turn and computes
p50 / p95 summaries per stage.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import cast

import structlog

from services.agent_orchestrator.models import TurnLatencyMetrics

logger = structlog.get_logger("agent_orchestrator.metrics")


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = pct / 100 * (len(sorted_vals) - 1)
    lower = math.floor(idx)
    upper = math.ceil(idx)
    if lower == upper:
        return sorted_vals[lower]
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


class MetricsCollector:
    def __init__(self) -> None:
        self._records: list[dict[str, float | str | None]] = []

    def record(self, turn_id: str, metrics: TurnLatencyMetrics) -> None:
        row: dict[str, float | str | None] = {"turn_id": turn_id}
        row["stt_latency"] = metrics.stt_latency()
        row["llm_latency"] = metrics.llm_latency()
        row["tts_startup_latency"] = metrics.tts_startup_latency()
        row["total_response_latency"] = metrics.total_response_latency()
        row["total_turn_duration"] = metrics.total_turn_duration()
        self._records.append(row)
        logger.info("metrics_recorded", **{k: v for k, v in row.items() if k != "turn_id"})

    def summary(self) -> dict[str, dict[str, float | None]]:
        stages = [
            "stt_latency",
            "llm_latency",
            "tts_startup_latency",
            "total_response_latency",
            "total_turn_duration",
        ]
        result: dict[str, dict[str, float | None | int]] = {}
        for stage in stages:
            vals: list[float] = cast(
                list[float],
                [r[stage] for r in self._records if isinstance(r.get(stage), float)],
            )
            result[stage] = {
                "p50": _percentile(vals, 50),
                "p95": _percentile(vals, 95),
                "count": len(vals),
            }
        return result

    def dump_json(self, path: Path) -> None:
        data = {
            "records": self._records,
            "summary": self.summary(),
        }
        path.write_text(json.dumps(data, indent=2))
        logger.info("metrics_dumped", path=str(path))


# Module-level singleton shared across all sessions in a process
collector = MetricsCollector()
