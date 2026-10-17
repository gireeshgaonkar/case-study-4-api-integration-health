import unittest
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

from starter_kit.dashboard import create_server, render_dashboard
from starter_kit.health_report import (
    Request,
    assess_integrations,
    format_report,
    overall_status,
    parse_logs,
)


def request(
    integration: str,
    status: str,
    minute: int = 0,
    status_code: int | None = None,
) -> Request:
    return Request(
        integration=integration,
        timestamp=datetime(2026, 8, 4, 9, minute, tzinfo=timezone.utc),
        status=status,
        latency_ms=100 if status == "success" else 30_000,
        status_code=status_code,
    )


class ParseLogsTests(unittest.TestCase):
    def test_timeout_and_unknown_status_are_retained(self) -> None:
        parsed = parse_logs(
            {
                "logs": [
                    {
                        "integration": "Example",
                        "timestamp": "2026-08-04T09:00:00",
                        "status": "timeout",
                        "latency_ms": 30_000,
                    },
                    {
                        "integration": "Example",
                        "timestamp": "2026-08-04T09:05:00Z",
                        "status": "queued",
                        "latency_ms": 10,
                    },
                ]
            }
        )
        self.assertEqual([item.status for item in parsed], ["timeout", "queued"])
        self.assertTrue(all(item.timestamp.tzinfo == timezone.utc for item in parsed))

    def test_rejects_invalid_latency_with_record_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "Record 1.*latency_ms"):
            parse_logs(
                {
                    "logs": [
                        {
                            "integration": "Example",
                            "timestamp": "2026-08-04T09:00:00",
                            "status": "success",
                            "latency_ms": float("nan"),
                        }
                    ]
                }
            )

    def test_rejects_invalid_http_status_code(self) -> None:
        with self.assertRaisesRegex(ValueError, "status_code"):
            parse_logs(
                {
                    "logs": [
                        {
                            "integration": "Example",
                            "timestamp": "2026-08-04T09:00:00",
                            "status": "error",
                            "status_code": True,
                            "latency_ms": 100,
                        }
                    ]
                }
            )

    def test_rejects_missing_logs_list(self) -> None:
        with self.assertRaisesRegex(ValueError, '"logs" list'):
            parse_logs({})


class AssessmentTests(unittest.TestCase):
    def test_sample_dataset_classifications_and_timeout_count(self) -> None:
        import json
        from pathlib import Path

        data_path = Path(__file__).parents[1] / "data" / "integration_logs.json"
        requests = parse_logs(json.loads(data_path.read_text(encoding="utf-8")))
        _, _, results = assess_integrations(requests)
        by_name = {result.name: result for result in results}

        self.assertEqual(by_name["ADP Payroll Sync"].status, "Critical")
        self.assertEqual(by_name["DocuSign Envelope API"].status, "Critical")
        self.assertEqual(by_name["Greenhouse ATS Sync"].status, "Critical")
        self.assertEqual(by_name["Greenhouse ATS Sync"].failed_requests, 6)
        self.assertEqual(by_name["Slack Notifications"].status, "Healthy")
        self.assertEqual(
            by_name["Slack Notifications"].next_step,
            "No immediate action; continue routine monitoring.",
        )
        self.assertEqual(by_name["Workday Directory Sync"].status, "Healthy")
        self.assertEqual(overall_status(results), "Critical")

    def test_failure_thresholds_are_inclusive(self) -> None:
        at_degraded = [
            request("Degraded", status)
            for status in ("error", "success", "success", "success", "success")
        ]
        at_critical = [
            request(
                "Critical",
                "error" if index < 5 else "success",
                minute=index,
            )
            for index in range(10)
        ]

        _, _, results = assess_integrations(at_degraded + at_critical)
        by_name = {result.name: result for result in results}
        self.assertEqual(by_name["Degraded"].failure_rate_pct, 20.0)
        self.assertEqual(by_name["Degraded"].status, "Degraded")
        self.assertEqual(by_name["Critical"].failure_rate_pct, 50.0)
        self.assertEqual(by_name["Critical"].status, "Critical")

    def test_low_volume_is_not_reported_healthy(self) -> None:
        _, _, results = assess_integrations(
            [request("Sparse", "success", minute=index) for index in range(4)]
        )
        self.assertEqual(results[0].status, "Insufficient data")
        self.assertEqual(overall_status(results), "Insufficient data")

    def test_low_volume_failures_escalate_by_absolute_count(self) -> None:
        entries = [
            request("Two failures", "error", minute=0, status_code=500),
            request("Two failures", "error", minute=1, status_code=500),
            request("Two failures", "success", minute=2),
            request("Two failures", "success", minute=3),
            request("Three failures", "error", minute=0, status_code=500),
            request("Three failures", "error", minute=1, status_code=500),
            request("Three failures", "timeout", minute=2),
            request("Three failures", "success", minute=3),
        ]

        _, _, results = assess_integrations(entries)
        by_name = {result.name: result for result in results}
        self.assertEqual(by_name["Two failures"].status, "Degraded")
        self.assertEqual(by_name["Three failures"].status, "Critical")

    def test_unknown_status_counts_as_failure_and_is_explained(self) -> None:
        requests = [
            request("Unknown", "success", minute=index) for index in range(4)
        ] + [request("Unknown", "queued", minute=4)]
        _, _, results = assess_integrations(requests)

        self.assertEqual(results[0].failed_requests, 1)
        self.assertEqual(results[0].status, "Degraded")
        self.assertTrue(
            any("Unknown statuses counted as failures: queued" in reason
                for reason in results[0].reasons)
        )

    def test_cause_breakdown_and_next_step_use_http_codes(self) -> None:
        entries = [
            request("Rate limited", "error", minute=index, status_code=429)
            for index in range(4)
        ] + [
            request("Rate limited", "success", minute=4, status_code=200)
        ]
        _, _, results = assess_integrations(entries)

        self.assertEqual(
            results[0].failure_cause_counts,
            {"HTTP 429 rate limit": 4},
        )
        self.assertEqual(results[0].status_code_counts, {429: 4})
        self.assertIn("quotas", results[0].next_step)

    def test_report_prioritizes_critical_and_shows_next_step(self) -> None:
        entries = [
            request(
                "Critical service",
                "error" if index < 3 else "success",
                minute=index,
                status_code=500 if index < 3 else 200,
            )
            for index in range(5)
        ] + [
            request("Healthy service", "success", minute=index)
            for index in range(5)
        ]
        start, end, results = assess_integrations(entries)
        report = format_report(start, end, results)

        self.assertLess(
            report.index("Critical service"),
            report.index("Healthy service"),
        )
        self.assertIn("Next step: Check the provider status", report)

    def test_window_is_inclusive_and_relative_to_latest_log(self) -> None:
        entries = [
            Request(
                "Windowed",
                datetime(2026, 8, 4, 8, 59, 59, tzinfo=timezone.utc),
                "error",
                10,
            ),
            request("Windowed", "success", minute=0),
            request("Windowed", "success", minute=5),
        ]
        start, end, results = assess_integrations(entries, timedelta(minutes=5))

        self.assertEqual(start, datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 8, 4, 9, 5, tzinfo=timezone.utc))
        self.assertEqual(results[0].total_requests, 2)
        self.assertEqual(results[0].status, "Insufficient data")

    def test_empty_input_and_report(self) -> None:
        start, end, results = assess_integrations([])
        self.assertIsNone(start)
        self.assertIsNone(end)
        self.assertEqual(overall_status(results), "Insufficient data")
        self.assertIn("no request data", format_report(start, end, results))

    def test_rejects_non_positive_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            assess_integrations([request("A", "success")], timedelta(0))


class DashboardTests(unittest.TestCase):
    def test_dashboard_escapes_untrusted_log_text(self) -> None:
        requests = parse_logs(
            {
                "logs": [
                    {
                        "integration": '<script>alert("x")</script>',
                        "timestamp": "2026-08-04T09:00:00",
                        "status": "success",
                        "latency_ms": 100,
                    }
                ]
            }
        )
        start, end, results = assess_integrations(requests)
        page = render_dashboard(start, end, results)

        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('<script>alert("x")</script>', page)

    def test_local_server_serves_health_dashboard(self) -> None:
        data_path = Path(__file__).parents[1] / "data" / "integration_logs.json"
        server = create_server(data_path, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(
                f"http://127.0.0.1:{server.server_port}/", timeout=5
            ) as response:
                page = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertEqual(
                    response.headers["Content-Type"], "text/html; charset=utf-8"
                )
            self.assertIn("Integration health", page)
            self.assertIn("Greenhouse ATS Sync", page)
            self.assertIn("Critical", page)
            self.assertIn("HTTP 429 rate limit", page)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
