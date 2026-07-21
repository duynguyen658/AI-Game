# Data Analysis Guide

Upload UTF-8 CSV through `/data-analysis/tasks`. Files, rows, and columns are bounded. Headers are normalized, invalid numeric values fail safely, previews neutralize spreadsheet formulas, and unsupported columns are reported.

Python calculates CTR, CPC, CPA, conversion rate, ROAS, retention, missing values, duplicates, segments, trend deltas, and anomaly indicators. Financial values use `Decimal`. The LLM may explain computed metrics but cannot replace source arithmetic. Poll the returned job or task endpoint, then read the structured report.
