#!/usr/bin/env python3
"""
Summarise latency metrics from the agent orchestrator /metrics endpoint
or from a JSON dump file.

Usage:
    # From live service
    python scripts/summarize_metrics.py --url http://localhost:8004/metrics

    # From a JSON dump file
    python scripts/summarize_metrics.py --file metrics_dump.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def print_table(summary: dict) -> None:
    print(f"\n{'Stage':<30} {'p50 (s)':>10} {'p95 (s)':>10} {'Count':>8}")
    print("-" * 62)
    for stage, data in summary.items():
        p50 = data.get("p50")
        p95 = data.get("p95")
        count = data.get("count", 0)
        p50_str = f"{p50:.3f}" if p50 is not None else "—"
        p95_str = f"{p95:.3f}" if p95 is not None else "—"
        print(f"{stage:<30} {p50_str:>10} {p95_str:>10} {count:>8}")
    print()


def from_url(url: str) -> None:
    import urllib.request

    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read())
    print_table(data.get("summary", data))


def from_file(path: Path) -> None:
    data = json.loads(path.read_text())
    summary = data.get("summary", data)
    print_table(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise agent latency metrics")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="HTTP URL of /metrics endpoint")
    group.add_argument("--file", type=Path, help="Path to JSON dump file")
    args = parser.parse_args()

    if args.url:
        from_url(args.url)
    else:
        from_file(args.file)


if __name__ == "__main__":
    main()
