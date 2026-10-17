# API Integration Health — Solution Design

## Problem

Brightline HR's Platform Ops team learns about third-party integration failures
from customer support tickets, sometimes days after a failure begins. The team
needs a fast, explainable view of which integrations need attention and what
action to take, without reading raw request logs.

The v1 is a repeatable report over the supplied request log data. It is not a
live monitoring service, alerting system, or replacement for customer-approved
service-level objectives.

## Assumptions and decisions

- Any status other than `success` is a failed request, including `error`,
  `timeout`, and unfamiliar future values. This conservative definition avoids
  silently treating new failure states as successes.
- When present, HTTP status codes are retained to distinguish useful triage
  signatures: HTTP 429 rate limits, HTTP 5xx server responses, HTTP 4xx
  client/auth responses, and timeouts. All still count as failed requests in
  this v1; the log schema does not provide enough context to decide whether a
  4xx is harmless input validation, a tenant-specific auth issue, or a systemic
  integration problem.
- Evaluate an inclusive trailing 60-minute window ending at the newest event
  timestamp. This makes seed-data replay deterministic and independent of the
  local clock.
- Use provisional integration-specific failure-rate thresholds where the
  business context suggests different consequence:
  - ADP Payroll Sync: Degraded at 5%, Critical at 15%.
  - DocuSign Envelope API: Degraded at 10%, Critical at 25%.
  - Other integrations: Degraded at 20%, Critical at 50%.
  These are discussion defaults only, not approved SLOs. They should be
  validated with Ops and incident history before operational use.
- For fewer than five requests, avoid relying on a volatile percentage: zero
  failures is **Insufficient data**, one or two failures is **Degraded**, and
  three or more failures is **Critical**. The absolute count guardrail is a
  provisional safety policy, not a statistical confidence claim.
- Successful-request average latency is displayed for context, but it does
  not alter health until Brightline provides meaningful latency SLOs. Timeout
  events count as failures and appear in the cause breakdown.
- Overall status is the worst integration status, so healthy services cannot
  average away a failing payroll or signature integration.
- The logs only identify integrations that emitted events. Detecting an
  integration that emitted no logs requires an expected-integration inventory
  and a freshness expectation; those are not present in the seed data.

## Proposed approach

Use a dependency-free Python CLI and a small local browser dashboard backed by
the same health calculation. Validate JSON records and normalize timestamps
to UTC; fail with a record-specific error on malformed input rather than
filling missing values with invented defaults. Group events into the
evaluation window, compute per-integration volume, failure rate, successful
request latency, status and HTTP-code counts, then apply the documented
threshold policy. The dashboard serves locally, rereads the input on each
request, and refreshes in the browser; it does not introduce separate metric
or classification logic.

The morning report sorts integrations by severity and explains the dominant
failure signature with a deterministic next step. For example, HTTP 429s
suggest reviewing provider quotas, concurrency, and retry/backoff; HTTP 5xx
responses suggest checking provider status and failed-request queue behavior;
timeouts suggest checking provider latency and worker timeout/retry settings.
These are investigation leads, not asserted root causes.

Thresholds, metric calculation, and presentation are kept separate enough to
make policy changes testable. The report has no external service dependency
and does not use AI to make classification decisions.

## Trade-offs

| Decision | Chosen for v1 | Alternative / trade-off |
| --- | --- | --- |
| Health model | Explicit states and threshold reasons | Composite score is compact but can hide whether the issue is volume, errors, or latency. |
| Failure causes | Show available HTTP status signatures; count all non-success statuses as failures | Excluding 4xx might reduce noise but could hide auth or schema problems without tenant and endpoint context. |
| Thresholds | Small set of provisional per-integration overrides with shared fallback | Fully customer-configurable SLOs are better for production but need stakeholder input and configuration lifecycle. |
| Low volume | Absolute failure-count guardrail below five requests | A percentage alone can make one failure out of two look catastrophic, or low traffic look healthy. |
| Latency | Display successful-request average only | p95 and latency gates need more volume and agreed integration-specific targets. |
| Roll-up | Worst integration status | An average can conceal a localized but high-impact failure. |
| Delivery | CLI plus a lightweight localhost dashboard over seed JSON | A deployed dashboard, scheduler, and streaming ingestion add operational choices beyond this take-home's evidence. |
| AI | Excluded from core v1 | Optional narrative can be added later, downstream of computed facts and with explicit data-sharing approval. |

## What I would validate and do next

First, review thresholds and status semantics with Marcus and the owners of
payroll, e-signature, ATS, directory sync, and notifications. In particular,
confirm whether retries eventually succeeding changes the customer-impact
metric, and whether 4xx errors should be attributed to a tenant or to the
platform. The current seed logs lack `tenant_id`, `job_id`, and retry outcome,
so they cannot distinguish a single customer's credential issue from a
provider-wide outage or an HTTP attempt failure from a terminal business-job
failure.

Then replay historical logs against known incidents and support tickets to
measure false alarms and missed issues, tune per-integration SLOs, and decide
the morning reporting window and freshness rules. With production data, add an
expected-integration inventory, no-telemetry checks, retry/job correlation,
tenant-level blast-radius analysis, historical trends, and alert routing with
clear ownership and runbooks. Add a dashboard or generated narrative only if
the Ops workflow demonstrates a need beyond the explainable CLI report.
