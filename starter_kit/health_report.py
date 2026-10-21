"""Generate an explainable health report from integration request logs."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

WINDOW = timedelta(minutes=60)
MIN_REQUESTS = 5
DEGRADED_FAILURE_RATE_PCT = 20.0
CRITICAL_FAILURE_RATE_PCT = 50.0
LOW_VOLUME_DEGRADED_FAILURES = 1
LOW_VOLUME_CRITICAL_FAILURES = 3
INTEGRATION_THRESHOLDS = {
    "ADP Payroll Sync": (5.0, 15.0),
    "DocuSign Envelope API": (10.0, 25.0),
}
KNOWN_STATUSES = {"success", "error", "timeout"}
HEALTH_ORDER = {
    "Healthy": 0,
    "Insufficient data": 1,
    "Degraded": 2,
    "Critical": 3,
}


@dataclass(frozen=True)
class Request:
    integration: str
    timestamp: datetime
    status: str
    latency_ms: float
    status_code: int | None = None


@dataclass(frozen=True)
class IntegrationHealth:
    name: str
    status: str
    total_requests: int
    failed_requests: int
    failure_rate_pct: float | None
    average_success_latency_ms: float | None
    status_counts: dict[str, int]
    failure_cause_counts: dict[str, int]
    status_code_counts: dict[int, int]
    degraded_threshold_pct: float
    critical_threshold_pct: float
    reasons: tuple[str, ...]
    next_step: str


def parse_timestamp(value: Any, record_number: int) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Record {record_number}: timestamp must be a string.")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"Record {record_number}: invalid timestamp {value!r}."
        ) from error
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def parse_logs(data: Any) -> list[Request]:
    if not isinstance(data, dict) or not isinstance(data.get("logs"), list):
        raise ValueError('Input must be a JSON object containing a "logs" list.')

    requests: list[Request] = []
    for record_number, entry in enumerate(data["logs"], start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Record {record_number}: each log must be an object.")

        integration = entry.get("integration")
        if not isinstance(integration, str) or not integration.strip():
            raise ValueError(
                f"Record {record_number}: integration must be a non-empty string."
            )

        status = entry.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError(
                f"Record {record_number}: status must be a non-empty string."
            )
        status = status.strip().lower()

        latency = entry.get("latency_ms")
        if (
            isinstance(latency, bool)
            or not isinstance(latency, (int, float))
            or not math.isfinite(latency)
            or latency < 0
        ):
            raise ValueError(
                f"Record {record_number}: latency_ms must be a finite, "
                "non-negative number."
            )

        status_code = entry.get("status_code")
        if status_code is not None and (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code <= 599
        ):
            raise ValueError(
                f"Record {record_number}: status_code must be an HTTP status "
                "integer from 100 to 599, or null."
            )
        if status == "success" and status_code is not None and status_code >= 400:
            raise ValueError(
                f"Record {record_number}: status is 'success' but "
                f"status_code is {status_code}."
            )

        requests.append(
            Request(
                integration=integration.strip(),
                timestamp=parse_timestamp(entry.get("timestamp"), record_number),
                status=status,
                latency_ms=float(latency),
                status_code=status_code,
            )
        )
    return requests


def assess_integrations(
    requests: list[Request], window: timedelta = WINDOW
) -> tuple[datetime | None, datetime | None, list[IntegrationHealth]]:
    if window <= timedelta(0):
        raise ValueError("The reporting window must be greater than zero.")
    if not requests:
        return None, None, []

    latest = max(request.timestamp for request in requests)
    window_start = latest - window
    in_window = [
        request
        for request in requests
        if window_start <= request.timestamp <= latest
    ]

    by_integration: dict[str, list[Request]] = defaultdict(list)
    for request in in_window:
        by_integration[request.integration].append(request)

    results: list[IntegrationHealth] = []
    for name, entries in sorted(by_integration.items()):
        status_counts = Counter(entry.status for entry in entries)
        failures = [
            entry for entry in entries if entry.status != "success"
        ]
        failure_causes = Counter(
            failure_cause(entry) for entry in failures
        )
        status_code_counts = Counter(
            entry.status_code for entry in failures if entry.status_code is not None
        )
        failure_rate = len(failures) / len(entries) * 100
        degraded_threshold, critical_threshold = INTEGRATION_THRESHOLDS.get(
            name,
            (DEGRADED_FAILURE_RATE_PCT, CRITICAL_FAILURE_RATE_PCT),
        )
        successful_latencies = [
            entry.latency_ms for entry in entries if entry.status == "success"
        ]
        average_latency = (
            sum(successful_latencies) / len(successful_latencies)
            if successful_latencies
            else None
        )
        unknown_statuses = sorted(set(status_counts) - KNOWN_STATUSES)

        reasons: list[str] = []
        if unknown_statuses:
            reasons.append(
                "Unknown statuses counted as failures: "
                + ", ".join(unknown_statuses)
                + "."
            )
        reasons.append(
            f"{len(failures)}/{len(entries)} requests failed "
            f"({failure_rate:.1f}%)."
        )
        if failure_causes:
            reasons.append(
                "Failure causes: "
                + ", ".join(
                    f"{cause}={count}"
                    for cause, count in sorted(
                        failure_causes.items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                )
                + "."
            )

        if len(entries) < MIN_REQUESTS:
            if len(failures) >= LOW_VOLUME_CRITICAL_FAILURES:
                health_status = "Critical"
                reasons.append(
                    f"At least {LOW_VOLUME_CRITICAL_FAILURES} failures in a "
                    f"low-volume sample (<{MIN_REQUESTS} requests)."
                )
            elif len(failures) >= LOW_VOLUME_DEGRADED_FAILURES:
                health_status = "Degraded"
                reasons.append(
                    "Failures were observed in a low-volume sample; "
                    "interpret the rate cautiously."
                )
            else:
                health_status = "Insufficient data"
                reasons.append(
                    f"Fewer than {MIN_REQUESTS} requests and no failures; "
                    "there is not enough evidence to call this healthy."
                )
        elif failure_rate >= critical_threshold:
            health_status = "Critical"
            reasons.append(
                f"Failure rate is at least the integration threshold "
                f"({critical_threshold:.0f}%)."
            )
        elif failure_rate >= degraded_threshold:
            health_status = "Degraded"
            reasons.append(
                f"Failure rate is at least the integration threshold "
                f"({degraded_threshold:.0f}%)."
            )
        else:
            health_status = "Healthy"
            reasons.append(
                f"Failure rate is below the integration threshold "
                f"({degraded_threshold:.0f}%)."
            )

        if average_latency is None:
            reasons.append("No successful requests are available for latency.")
        else:
            reasons.append(
                f"Successful-request average latency is "
                f"{average_latency:.0f} ms (informational; no latency SLO set)."
            )

        results.append(
            IntegrationHealth(
                name=name,
                status=health_status,
                total_requests=len(entries),
                failed_requests=len(failures),
                failure_rate_pct=failure_rate,
                average_success_latency_ms=average_latency,
                status_counts=dict(sorted(status_counts.items())),
                failure_cause_counts=dict(
                    sorted(
                        failure_causes.items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                ),
                status_code_counts=dict(sorted(status_code_counts.items())),
                degraded_threshold_pct=degraded_threshold,
                critical_threshold_pct=critical_threshold,
                reasons=tuple(reasons),
                next_step=recommended_next_step(failure_causes, health_status),
            )
        )
    return window_start, latest, results


def overall_status(results: list[IntegrationHealth]) -> str:
    if not results:
        return "Insufficient data"
    return max(results, key=lambda result: HEALTH_ORDER[result.status]).status


def failure_cause(request: Request) -> str:
    if request.status == "timeout":
        return "Timeout"
    if request.status_code == 429:
        return "HTTP 429 rate limit"
    if request.status_code is not None and 500 <= request.status_code <= 599:
        return "HTTP 5xx server error"
    if request.status_code is not None and 400 <= request.status_code <= 499:
        return "HTTP 4xx client/auth error"
    if request.status not in KNOWN_STATUSES:
        return f"Unknown status ({request.status})"
    return f"Failed status ({request.status})"


def recommended_next_step(
    failure_causes: Counter[str], health_status: str
) -> str:
    if health_status == "Healthy":
        return "No immediate action; continue routine monitoring."
    if health_status == "Insufficient data":
        return "Collect more request data before treating this integration as healthy."
    if not failure_causes:
        return "No action required; continue monitoring."
    primary_cause = failure_causes.most_common(1)[0][0]
    if primary_cause == "HTTP 429 rate limit":
        return "Review provider quotas, request concurrency, and retry/backoff behavior."
    if primary_cause == "HTTP 5xx server error":
        return "Check the provider status and inspect retry/queue behavior for failed requests."
    if primary_cause == "Timeout":
        return "Check provider latency and verify worker timeout and retry settings."
    if primary_cause == "HTTP 4xx client/auth error":
        return "Inspect authentication, permissions, and request payloads; tenant attribution is unavailable."
    if primary_cause.startswith("Unknown status"):
        return "Inspect the unfamiliar status and update the failure mapping if its semantics are confirmed."
    return "Inspect failed request details and confirm how their status should be interpreted."


def format_report(
    window_start: datetime | None,
    window_end: datetime | None,
    results: list[IntegrationHealth],
) -> str:
    lines = [f"OVERALL HEALTH: {overall_status(results)}"]
    if window_start is None or window_end is None:
        lines.append("Window: no request data")
        lines.append("No integration request logs were found.")
        return "\n".join(lines)

    lines.append(
        "Window (UTC): "
        f"{window_start:%Y-%m-%d %H:%M} to {window_end:%Y-%m-%d %H:%M}"
    )
    if not results:
        lines.append("No requests fall inside the reporting window.")
        return "\n".join(lines)

    lines.append("")
    lines.append(
        f"{'Integration':<26} {'Health':<19} {'Failed':>8} "
        f"{'Failure rate':>14} {'Avg success ms':>16}"
    )
    lines.append("-" * 88)
    prioritized = sorted(
        results,
        key=lambda result: (-HEALTH_ORDER[result.status], result.name),
    )
    for result in prioritized:
        latency = (
            f"{result.average_success_latency_ms:.0f}"
            if result.average_success_latency_ms is not None
            else "n/a"
        )
        rate = (
            f"{result.failure_rate_pct:.1f}%"
            if result.failure_rate_pct is not None
            else "n/a"
        )
        lines.append(
            f"{result.name:<26.26} {result.status:<19} "
            f"{result.failed_requests:>3}/{result.total_requests:<4} "
            f"{rate:>14} {latency:>16}"
        )
        lines.append("  Why: " + " ".join(result.reasons))
        lines.append(
            "  Status counts: "
            + ", ".join(
                f"{status}={count}"
                for status, count in result.status_counts.items()
            )
        )
        if result.status_code_counts:
            lines.append(
                "  Failed HTTP codes: "
                + ", ".join(
                    f"{status_code}={count}"
                    for status_code, count in result.status_code_counts.items()
                )
            )
        lines.append("  Next step: " + result.next_step)
    return "\n".join(lines)


def run(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as input_file:
            requests = parse_logs(json.load(input_file))
        start, end, results = assess_integrations(requests)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print(format_report(start, end, results))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize third-party integration health from request logs."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "data" / "integration_logs.json",
        help="Path to a JSON log file (defaults to the bundled seed data).",
    )
    return run(parser.parse_args().input)


if __name__ == "__main__":
    raise SystemExit(main())
