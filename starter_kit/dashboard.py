"""Serve a simple local dashboard for integration health logs."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if __package__:
    from .health_report import (
        HEALTH_ORDER,
        IntegrationHealth,
        assess_integrations,
        overall_status,
        parse_logs,
    )
else:
    from health_report import (
        HEALTH_ORDER,
        IntegrationHealth,
        assess_integrations,
        overall_status,
        parse_logs,
    )

STATUS_CLASS = {
    "Healthy": "healthy",
    "Insufficient data": "insufficient",
    "Degraded": "degraded",
    "Critical": "critical",
}


def load_health(
    input_path: Path,
) -> tuple[datetime | None, datetime | None, list[IntegrationHealth]]:
    with input_path.open(encoding="utf-8") as input_file:
        requests = parse_logs(json.load(input_file))
    return assess_integrations(requests)


def render_dashboard(
    window_start: datetime | None,
    window_end: datetime | None,
    results: list[IntegrationHealth],
) -> str:
    summary = overall_status(results)
    status_class = STATUS_CLASS[summary]
    if window_start is None or window_end is None:
        window_label = "No request data"
    else:
        window_label = (
            f"{window_start:%Y-%m-%d %H:%M} to "
            f"{window_end:%Y-%m-%d %H:%M} UTC"
        )

    cards = []
    for result in sorted(
        results,
        key=lambda item: (-HEALTH_ORDER[item.status], item.name),
    ):
        card_class = STATUS_CLASS[result.status]
        failure_rate = (
            f"{result.failure_rate_pct:.1f}%"
            if result.failure_rate_pct is not None
            else "n/a"
        )
        latency = (
            f"{result.average_success_latency_ms:.0f} ms"
            if result.average_success_latency_ms is not None
            else "n/a"
        )
        causes = ", ".join(
            f"{html.escape(cause)}: {count}"
            for cause, count in result.failure_cause_counts.items()
        ) or "No failures recorded"
        counts = ", ".join(
            f"{html.escape(status)}: {count}"
            for status, count in result.status_counts.items()
        )
        reasons = "".join(
            f"<li>{html.escape(reason)}</li>" for reason in result.reasons
        )
        cards.append(
            f"""
            <article class="card {card_class}">
              <div class="card-header">
                <h2>{html.escape(result.name)}</h2>
                <span class="badge">{html.escape(result.status)}</span>
              </div>
              <div class="metrics">
                <div><span>Requests</span><strong>{result.total_requests}</strong></div>
                <div><span>Failed</span><strong>{result.failed_requests}</strong></div>
                <div><span>Failure rate</span><strong>{failure_rate}</strong></div>
                <div><span>Avg. success latency</span><strong>{latency}</strong></div>
              </div>
              <p><b>Failure causes:</b> {causes}</p>
              <p><b>Status counts:</b> {counts}</p>
              <ul>{reasons}</ul>
              <p class="next-step"><b>Next step:</b> {html.escape(result.next_step)}</p>
            </article>
            """
        )

    empty_message = (
        '<p class="empty">No integration logs are available for this report.</p>'
        if not results
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>Brightline Integration Health</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, Segoe UI, sans-serif; }}
    body {{ margin: 0; background: #f3f6fb; color: #17233b; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 28px 18px; }}
    header {{ display: flex; flex-wrap: wrap; justify-content: space-between;
              align-items: center; gap: 12px; margin-bottom: 22px; }}
    h1 {{ margin: 0; font-size: 1.7rem; }}
    .muted {{ color: #5a667a; margin: 6px 0 0; }}
    .overall {{ padding: 10px 16px; border-radius: 8px; font-weight: 750; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
              gap: 16px; }}
    .card {{ background: white; border: 1px solid #d9e1ed; border-left: 6px solid;
             border-radius: 10px; padding: 18px; box-shadow: 0 2px 8px #17233b0b; }}
    .card-header {{ display: flex; justify-content: space-between; gap: 8px;
                    align-items: start; }}
    h2 {{ margin: 0; font-size: 1.12rem; }}
    .badge {{ white-space: nowrap; border-radius: 999px; padding: 4px 10px;
              font-size: .8rem; font-weight: 700; }}
    .metrics {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;
                margin: 18px 0; }}
    .metrics div {{ background: #f5f7fb; border-radius: 7px; padding: 10px; }}
    .metrics span {{ display: block; color: #5a667a; font-size: .78rem; }}
    .metrics strong {{ display: block; margin-top: 3px; }}
    p, li {{ line-height: 1.45; }}
    ul {{ padding-left: 20px; }}
    .next-step {{ background: #f5f7fb; padding: 10px; border-radius: 7px; }}
    .healthy {{ border-color: #17844b; }}
    .healthy .badge, .overall.healthy {{ background: #dff5e8; color: #116137; }}
    .degraded {{ border-color: #c07800; }}
    .degraded .badge, .overall.degraded {{ background: #fff0ce; color: #704400; }}
    .critical {{ border-color: #c73535; }}
    .critical .badge, .overall.critical {{ background: #fde4e4; color: #8d2020; }}
    .insufficient {{ border-color: #69758a; }}
    .insufficient .badge, .overall.insufficient {{ background: #e8edf4; color: #3f4a5d; }}
    .empty {{ background: white; padding: 22px; border-radius: 9px; }}
    footer {{ color: #5a667a; margin-top: 22px; font-size: .85rem; }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Integration health</h1>
        <p class="muted">Brightline HR · Window: {html.escape(window_label)}</p>
      </div>
      <div class="overall {status_class}">Overall: {html.escape(summary)}</div>
    </header>
    {empty_message}
    <section class="cards">{"".join(cards)}</section>
    <footer>Refreshes every 60 seconds. Latency is informational; thresholds are provisional.</footer>
  </main>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def __init__(self, *args: object, input_path: Path, **kwargs: object) -> None:
        self.input_path = input_path
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if self.path not in ("/", "/index.html"):
            self.send_error(404, "Not found")
            return
        try:
            start, end, results = load_health(self.input_path)
            body = render_dashboard(start, end, results)
            status = 200
        except (OSError, json.JSONDecodeError, ValueError) as error:
            body = (
                "<!doctype html><html><head><meta charset=\"utf-8\">"
                "<title>Dashboard input error</title></head><body>"
                "<h1>Unable to load health data</h1><pre>"
                + html.escape(str(error))
                + "</pre></body></html>"
            )
            status = 500

        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)


def create_server(input_path: Path, host: str, port: int) -> HTTPServer:
    handler = partial(DashboardHandler, input_path=input_path)
    return HTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve a local browser dashboard for integration health."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "data" / "integration_logs.json",
        help="Path to a JSON log file (defaults to the bundled seed data).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (defaults to localhost; use other addresses only on trusted networks).",
    )
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000).")
    args = parser.parse_args()

    try:
        server = create_server(args.input, args.host, args.port)
    except OSError as error:
        parser.error(f"could not start dashboard server: {error}")
    print(f"Dashboard available at http://{args.host}:{server.server_port}/")
    print(f"Reading logs from: {args.input}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
