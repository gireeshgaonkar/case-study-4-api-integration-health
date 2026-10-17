# Starter Kit — API Integration Health

## Contents

- `data/integration_logs.json` — 60 synthetic request-log entries across 5 third-party integrations (Slack, ADP, DocuSign, Workday, Greenhouse) over about an hour.
- `integration_utils.py` — a small, optional Python utility module with basic error-rate and latency helpers, provided as a rough starting point.
- `health_report.py` — dependency-free health assessment CLI.
- `dashboard.py` — local browser dashboard using the same health assessment.
- `tests/test_health_report.py` — focused standard-library unit tests.

## Run the report

From the project root, run `python starter_kit\health_report.py`. See the
top-level `README.md` for input format, assumptions, and test instructions.

To start the local dashboard, run `python starter_kit\dashboard.py` and open
`http://127.0.0.1:8000/` in a browser.

## Notes

- You're free to use, modify, replace, or ignore `integration_utils.py` entirely — it's not guaranteed to be complete, optimal, or bug-free.
- Not every request in the log necessarily has status `"success"` or `"error"` — worth checking what other status values show up in the data and whether your (or the provided) logic accounts for all of them.
