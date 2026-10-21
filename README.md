# API Integration Health

A small, dependency-free Python application with a local browser dashboard as
the primary v1 operator view and a CLI for direct report output. It summarizes
third-party integration health from Brightline HR's supplied request-log seed
data.

## Requirements

- Python 3.10 or newer
- No third-party Python packages

## CLI report

From the project root:

```powershell
python starter_kit\health_report.py
```

Pass a different JSON file as the first argument:

```powershell
python starter_kit\health_report.py path\to\integration_logs.json
```

## V1 dashboard

The browser dashboard is the primary v1 interface. It provides an at-a-glance
overall health banner and one card per integration. Cards show request and
failure counts, failure rate, average successful-request latency, failure
causes, status counts, the reasons for the health classification, and a
suggested next step. Integrations are ordered by severity so the items needing
attention appear first.

Start the local web server from the project root:

```powershell
python starter_kit\dashboard.py
```

Then open <http://127.0.0.1:8000/> in a browser. The dashboard uses the same
assessment logic and thresholds as the CLI. It displays the evaluated UTC
window and refreshes the page every 60 seconds; each page request rereads and
reassesses the JSON input file. To use another input file or port, pass
arguments:

```powershell
python starter_kit\dashboard.py path\to\integration_logs.json --port 8080
```

The server uses only Python's standard library and binds to `127.0.0.1` by
default. It is intended for local demonstration, not public deployment; there
is no authentication or TLS. Binding to another host can expose the report to
other machines on that network. Stop the server with `Ctrl+C`.

The page reads the provided log file; the 60-second refresh is **not** a live
connection to Brightline's production logging system and does not make the
underlying data fresher.

The input must be a JSON object with a `logs` array. Each record must have a
non-empty `integration`, an ISO-8601 `timestamp`, a non-empty `status`, and a
finite non-negative `latency_ms`. An optional `status_code` must be an HTTP
status integer from 100 to 599 or `null`.

## Example output (seed data)

```text
OVERALL HEALTH: Critical
Window (UTC): 2026-08-04 08:55 to 2026-08-04 09:55

Integration                Health                Failed   Failure rate   Avg success ms
----------------------------------------------------------------------------------------
ADP Payroll Sync            Critical              5/12          41.7%              223
  Why: 5/12 requests failed (41.7%). Failure causes: HTTP 5xx server error=5. Failure rate is at least the integration threshold (15%).
  Next step: Check the provider status and inspect retry/queue behavior for failed requests.
...
Greenhouse ATS Sync         Critical              6/12          50.0%              199
```

The CLI report sorts by severity and includes status counts, HTTP code counts,
failure causes, and a deterministic suggested next step. The browser dashboard
sorts by severity, then descending failure rate, then integration name.
Recommendations are triage leads, not confirmed root causes.

## Run tests

From the project root:

```powershell
python -m unittest discover -s starter_kit\tests -v
```

## Assumptions and limitations

- Every status except `success` (including `error`, `timeout`, and unknown
  statuses) counts as a failed request. HTTP code breakdowns help distinguish
  429 rate limits, 5xx server responses, and 4xx client/auth responses, but
  they do not change the basic failure definition. Records that claim
  `success` with an HTTP 4xx/5xx code are rejected as contradictory input.
- The trailing 60-minute window is anchored to the newest timestamp in the
  input and includes both window boundaries. Seed data therefore produces a
  deterministic report regardless of the current date.
- With fewer than five requests, zero failures means **Insufficient data**,
  one or two failures means **Degraded**, and three or more means **Critical**.
  At higher volume, ADP Payroll uses provisional 5%/15% degraded/critical
  thresholds, DocuSign uses 10%/25%, and Greenhouse ATS uses the shared
  20%/50% thresholds. These are assumptions to validate with Ops, not
  production SLOs.
- Average latency is calculated only from successful requests and is
  informational; it does not change health status.
- HTTP codes cannot identify tenant-specific authentication issues or
  distinguish retried attempts from terminal job failures because the seed
  logs contain no tenant or job/retry identifiers.
- Overall health is the worst integration result. Integrations with no log
  records cannot be discovered without an external integration inventory.
- This is a local batch report over provided logs. The browser dashboard is a
  thin view over the same calculations; it has no live ingestion, scheduled
  collection, freshness checks, alerts, customer-specific configuration, or
  persistent history. Threshold overrides are currently edited in the source
  rather than loaded from a customer-facing configuration file.
- The brief says Brightline has request logs but does not identify the logging
  platform, access method, retention, or freshness. The provided file is
  synthetic seed data, so a production data-source adapter remains to be
  scoped with Brightline.

See [SOLUTION_DESIGN.md](SOLUTION_DESIGN.md) for the design rationale,
trade-offs, and recommended next steps.
