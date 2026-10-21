# API Integration Health — Solution Design

**Customer:** Brightline HR

## Problem

Brightline HR's Platform Ops team usually learns about integration failures
from customer tickets, sometimes days after they begin. Marcus needs a morning
view that identifies integrations needing attention and explains why, without
requiring Ops to search raw request logs. The prototype demonstrates that view
against the supplied synthetic request data; it is not yet connected to
Brightline's production telemetry.

## Assumptions and health rules

- Any non-`success` status, including `error`, `timeout`, and unfamiliar
  statuses, is a failed request. A record claiming `success` with an HTTP
  4xx/5xx code is rejected as contradictory input.
- When available, HTTP codes explain failure signatures (429 rate limits,
  5xx server responses, 4xx client/auth responses). They do not override the
  failure definition: tenant, retry, and business-job context are absent, so
  this version cannot safely decide which errors are harmless or isolated.
- Assess an inclusive trailing 60-minute window ending at the newest event.
  This matches the roughly one-hour fixture and makes replay deterministic;
  it is not a production-window recommendation.
- At five or more requests, provisional thresholds are:

  | Integration | Degraded | Critical |
  | --- | ---: | ---: |
  | ADP Payroll Sync | 5% | 15% |
  | DocuSign Envelope API | 10% | 25% |
  | Greenhouse ATS Sync and others | 20% | 50% |

  These are discussion defaults, not customer-approved SLOs. Validate them
  with Ops and historical incidents before operational use.
- Below five requests, zero failures means **Insufficient data**, one or two
  failures means **Degraded**, and three or more means **Critical**. This
  absolute-count guardrail is provisional and not a statistical guarantee.
- Successful-request average latency is informational, not a health gate;
  latency targets require Brightline-approved SLOs. Overall health is the
  worst integration status so one failure cannot be averaged away.
- An integration with no events is invisible without an expected-integration
  inventory and freshness/schedule information.

## V1 design

The primary v1 operator interface is a dependency-free localhost dashboard;
a CLI is also provided for direct report output. Both share one assessment
pipeline. It validates the JSON schema, normalizes timestamps to UTC, applies
the window and thresholds, then reports request counts, failure rate,
successful-request average latency, status/HTTP-code breakdowns, reasons, and
a suggested investigation step. The CLI sorts by severity; the dashboard
breaks ties by descending failure rate and then integration name.

The browser page is read-only, served by Python's standard-library HTTP
server. It displays an overall health banner and severity-ordered integration
cards. Log-derived text is HTML-escaped. The page refreshes every 60 seconds
and rereads the JSON file on each request; it does not ingest telemetry or
make stale source data fresher. The server binds to localhost by default and
has no authentication or TLS, so it is for local demonstration only.
Malformed input produces an explicit error rather than synthetic health data.

## Trade-offs

| Choice | Rationale and limitation |
| --- | --- |
| Explicit status bands and reasons | Easier to explain and act on than a composite score; thresholds still need validation. |
| Count all non-success outcomes | Avoids hiding timeouts or new statuses; 4xx classification may need tenant/business context. |
| Integration-specific defaults | Reflects differing potential impact; names and cutoffs are provisional and source-configured. |
| Average successful latency | Simple context for a small fixture; not a tail-latency SLO. |
| Worst-status roll-up | Keeps a serious integration issue visible rather than averaging it away. |
| Local dashboard as primary v1 plus CLI | Demonstrates the morning operator view and a simple direct-report path without assuming deployment infrastructure. |
| No AI in core path | Deterministic and auditable; any future summary should only describe computed facts. |

## V2 and V3

**V2 — Connect real telemetry.** First discover where Brightline's existing
logs are stored and validate access, schema, completeness, retention, and
freshness. Build the narrowest adapter into the existing assessment pipeline.
Show both recent health (a trailing 15-minute view with low-volume safeguards)
and a 24-hour morning summary in 15-minute buckets. Refresh cadence is separate
from reporting windows and should follow source-data freshness. Validate
thresholds against known incidents and tickets; add missing-data checks only
when Brightline provides expected integrations or schedules. Tenant-level
diagnosis requires suitable identifiers and privacy controls.

**V3 — Prefer existing observability; productize only for a proven gap.**
Assess Brightline's current platform for ingestion, these views and health
rules, freshness checks, alerting, access control, retention, and ownership.
If it meets the validated needs, implement dashboards and alerts there.
Productize this code only if a pilot demonstrates a material capability gap
or a dedicated workflow worth the ongoing engineering and support cost.
Compare fit, effort, security, total cost, and ownership, and test against
known incidents before replacing existing tools. Keep AI optional, downstream
of deterministic health results, and subject to data-sharing approval.
