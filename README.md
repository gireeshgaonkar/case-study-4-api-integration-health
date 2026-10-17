# API Integration Health

A small, dependency-free Python CLI that summarizes the health of third-party
integrations from Brightline HR's supplied request-log seed data.

## Requirements

- Python 3.10 or newer
- No third-party Python packages

## Run

From the project root:

```powershell
python starter_kit\health_report.py
```

Pass a different JSON file as the first argument:

```powershell
python starter_kit\health_report.py path\to\integration_logs.json
```

## Open the local dashboard

Start the local web server from the project root:

```powershell
python starter_kit\dashboard.py
```

Then open <http://127.0.0.1:8000/> in a browser. To use another input file or
port, pass arguments:

```powershell
python starter_kit\dashboard.py path\to\integration_logs.json --port 8080
```

The dashboard reloads and reassesses the input file whenever the page is
refreshed (it refreshes itself every 60 seconds). It binds to `127.0.0.1` by
default and is intended for local demonstration, not public deployment. Stop
the server with `Ctrl+C`.

The input must be a JSON object with a `logs` array. Each record must have a
non-empty `integration`, an ISO-8601 `timestamp`, a non-empty `status`, and a
finite non-negative `latency_ms`.

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

The report sorts by severity and includes status counts, HTTP code counts,
failure causes, and a deterministic suggested next step. Recommendations are
triage leads, not confirmed root causes.

## Run tests

From the project root:

```powershell
python -m unittest discover -s starter_kit\tests -v
```

## Assumptions and limitations

- Every status except `success` (including `error`, `timeout`, and unknown
  statuses) counts as a failed request. HTTP code breakdowns help distinguish
  429 rate limits, 5xx server responses, and 4xx client/auth responses, but
  they do not change the basic failure definition.
- The trailing 60-minute window is anchored to the newest timestamp in the
  input and includes both window boundaries. Seed data therefore produces a
  deterministic report regardless of the current date.
- With fewer than five requests, zero failures means **Insufficient data**,
  one or two failures means **Degraded**, and three or more means **Critical**.
  At higher volume, ADP Payroll uses provisional 5%/15% degraded/critical
  thresholds and DocuSign uses 10%/25%; other integrations use 20%/50%.
  These are assumptions to validate with Ops, not production SLOs.
- Average latency is calculated only from successful requests and is
  informational; it does not change health status.
- HTTP codes cannot identify tenant-specific authentication issues or
  distinguish retried attempts from terminal job failures because the seed
  logs contain no tenant or job/retry identifiers.
- Overall health is the worst integration result. Integrations with no log
  records cannot be discovered without an external integration inventory.
- This is a local batch report over provided logs. The browser dashboard is
  a thin view over the same calculations; it has no live ingestion, scheduled
  collection, freshness checks, alerts, customer-specific configuration, or
  persistent history. Threshold overrides are currently edited in the source
  rather than loaded from a customer-facing configuration file.

See [SOLUTION_DESIGN.md](SOLUTION_DESIGN.md) for the design rationale,
trade-offs, and recommended next steps.
