# Sales KPI Report

`sales_report.py` fetches sales records from a REST/JSON API, checks every record,
and writes an Excel KPI report. Bad records are left out of the figures and listed
with a reason, so you can use the report without checking it by hand.

## Setup

```bash
pip install -r requirements.txt
export SALES_API_TOKEN="your-token"   # optional, sent as "Authorization: Bearer ..."
```

## Run

```bash
python sales_report.py \
  --url https://api.example.com/v1/sales \
  --records-path data.items \
  --next-path links.next \
  --currency EUR \
  --date-from 2026-09-01 --date-to 2026-09-30 \
  --out reports/sales_2026-09.xlsx
```

Try it offline with the sample file:

```bash
python sales_report.py --input-file sample_data/sales.json --records-path data.items --currency EUR
```

### Options

| Option | Meaning |
|---|---|
| `--url` / `--input-file` | Where the data comes from: the API, or a JSON export. |
| `--records-path` | Where the list of records sits in the JSON, e.g. `data.items`. Leave it out if the response is the list itself. |
| `--next-path` | Where the next page URL sits, e.g. `links.next`. The script follows it until it is empty. |
| `--token-env` | Environment variable with the token (default `SALES_API_TOKEN`). |
| `--api-key-header` | Send the token in this header (e.g. `X-API-Key`) instead of `Authorization: Bearer`. |
| `--map FIELD=API_FIELD` | Use when the API uses other field names, e.g. `--map order_date=createdAt --map unit_price=price`. |
| `--currency` | Report currency. Records in another currency are excluded and logged. |
| `--date-from` / `--date-to` | Only include orders in this range. Records outside it are skipped, not counted as errors. |
| `--max-excluded-share` | If more records than this are excluded (default `0.05` = 5%), the script exits with code 2. |

### Expected record fields

| Field | Required | Notes |
|---|---|---|
| `order_id` | yes | Orders are counted by distinct `order_id`. |
| `order_date` | yes | `YYYY-MM-DD`, ISO date-time, `DD.MM.YYYY` or `YYYY/MM/DD`. |
| `quantity` | yes | Must be greater than 0. |
| `unit_price` | yes | Must be 0 or more. Revenue = quantity × unit price. |
| `line_id` | no | Used to spot duplicates. Without it, identical records count as duplicates. |
| `customer_id` | no | Adds "Distinct customers" and "Revenue per customer". |
| `currency` | no | If it holds more than one currency, `--currency` is required. |

## Output

An `.xlsx` file with two sheets. Each sheet has a visible watermark line at the top
and in the print header and footer, showing when and from which source it was made.

- **KPI Summary**: period, currency, total revenue, number of orders, units sold,
  average order value, average price per unit, average units per order, distinct
  customers, revenue per customer, and record counts (received / used / excluded).
- **Data Quality**: every excluded record with its position, order ID, reason and
  the raw data.

## Checks that keep the report correct

- Missing required fields, unreadable numbers or dates, dates in the future,
  quantity ≤ 0, negative prices, duplicate lines, and other currencies are
  excluded and logged.
- Amounts are calculated with exact decimals (no floating-point rounding errors)
  and rounded half-up to 2 places.
- Several currencies without `--currency` stop the run instead of adding them up.
- No report is written if the source returns nothing or no record is valid.
- Network errors and HTTP 429/5xx are retried with backoff; 401/403 stop with a clear message.

### Exit codes (for schedulers and pipelines)

| Code | Meaning |
|---|---|
| 0 | Report written, data quality within the limit. |
| 1 | No report written (connection, auth, format or configuration problem). |
| 2 | Report written, but more records than `--max-excluded-share` were excluded. |

## Tests

```bash
python -m unittest discover -s tests -v
```
