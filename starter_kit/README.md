# Starter Kit — API Integration Health

## Contents

- `data/integration_logs.json` — 60 synthetic request-log entries across 5 third-party integrations (Slack, ADP, DocuSign, Workday, Greenhouse) over about an hour.
- `health_report.py` — dependency-free health assessment CLI.
- `dashboard.py` — local browser dashboard using the same health assessment.
- `tests/test_health_report.py` — focused standard-library unit tests.

## Run the v1 dashboard

The dashboard is the primary operator-facing v1. From the project root, run
`python starter_kit\dashboard.py` and open `http://127.0.0.1:8000/` in a
browser. The CLI is also available with `python starter_kit\health_report.py`.
See the top-level `README.md` for input format, assumptions, and test
instructions.

## Notes

- The seed data includes `timeout` statuses as well as `success` and `error`.
  See the top-level `SOLUTION_DESIGN.md` for the chosen failure definition
  and provisional thresholds.
