#!/usr/bin/env python3
"""Fetch sales records from a REST/JSON API and write a KPI summary to Excel.

Every record is validated before it is counted. Records that fail a check are
left out of the KPIs and listed, with the reason, on the "Data Quality" sheet,
so the figures in the report can be used as they are.

Usage examples:
    python sales_report.py --url https://api.example.com/sales --out report.xlsx
    python sales_report.py --input-file sample_data/sales.json --out report.xlsx

See README.md for all options.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import requests
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

WATERMARK = "Generated automatically by sales_report.py"
CENT = Decimal("0.01")

# Canonical field name -> API field name. Override with --map canonical=api_field.
DEFAULT_FIELD_MAP = {
    "order_id": "order_id",
    "line_id": "line_id",
    "order_date": "order_date",
    "quantity": "quantity",
    "unit_price": "unit_price",
    "customer_id": "customer_id",
    "currency": "currency",
}
REQUIRED_FIELDS = ("order_id", "order_date", "quantity", "unit_price")
DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%d.%m.%Y", "%Y/%m/%d")

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_QUALITY_THRESHOLD = 2


class FatalError(Exception):
    """An error that makes a trustworthy report impossible."""


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #

def dig(obj: Any, dotted_path: str | None) -> Any:
    """Return obj["a"]["b"] for path "a.b"; the object itself for an empty path."""
    if not dotted_path:
        return obj
    for key in dotted_path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj


def fetch_records(url: str, token: str | None, api_key_header: str | None,
                  records_path: str | None, next_path: str | None,
                  timeout: float = 30.0, retries: int = 4,
                  max_pages: int = 10_000) -> list[dict]:
    """Fetch all pages from the API. Follows a "next page" URL if next_path is set."""
    headers = {"Accept": "application/json"}
    if token:
        if api_key_header:
            headers[api_key_header] = token
        else:
            headers["Authorization"] = f"Bearer {token}"

    records: list[dict] = []
    page_url: str | None = url
    pages = 0
    while page_url:
        pages += 1
        if pages > max_pages:
            raise FatalError(f"Stopped after {max_pages} pages; pagination looks endless.")
        payload = _get_json(page_url, headers, timeout, retries)
        page_records = dig(payload, records_path)
        if not isinstance(page_records, list):
            raise FatalError(
                f"Expected a JSON list at '{records_path or '<root>'}' in the API response "
                f"from {page_url}, got {type(page_records).__name__}. Set --records-path.")
        records.extend(page_records)
        page_url = dig(payload, next_path) if next_path else None
    return records


def _get_json(url: str, headers: dict, timeout: float, retries: int) -> Any:
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code in (401, 403):
                raise FatalError(f"API refused access ({resp.status_code}). Check the token.")
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt >= retries:
                raise FatalError(f"Could not reach {url}: {exc}") from exc
            time.sleep(delay)
            delay *= 2
        except requests.HTTPError as exc:
            raise FatalError(f"API returned an error for {url}: {exc}") from exc
        except ValueError as exc:
            raise FatalError(f"API response from {url} is not valid JSON.") from exc
    raise FatalError(f"API at {url} kept failing after {retries} retries.")


def load_records_from_file(path: Path, records_path: str | None) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FatalError(f"Could not read JSON from {path}: {exc}") from exc
    records = dig(payload, records_path)
    if not isinstance(records, list):
        raise FatalError(f"Expected a JSON list at '{records_path or '<root>'}' in {path}.")
    return records


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

@dataclass
class CleanRecord:
    order_id: str
    order_date: date
    quantity: Decimal
    unit_price: Decimal
    customer_id: str | None
    currency: str | None

    @property
    def revenue(self) -> Decimal:
        return self.quantity * self.unit_price


@dataclass
class Rejection:
    row_number: int
    order_id: str
    reason: str
    raw: str


@dataclass
class ValidationResult:
    clean: list[CleanRecord] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    received: int = 0
    out_of_period: int = 0

    @property
    def excluded_share(self) -> float:
        checked = self.received - self.out_of_period
        return len(self.rejected) / checked if checked else 0.0


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or _is_blank(value):
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def parse_date(value: Any) -> date | None:
    if _is_blank(value):
        return None
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def validate(records: Iterable[Any], field_map: dict[str, str],
             expected_currency: str | None = None,
             date_from: date | None = None, date_to: date | None = None,
             today: date | None = None) -> ValidationResult:
    """Split records into clean ones and rejected ones (with a reason each)."""
    today = today or date.today()
    result = ValidationResult()
    seen_keys: set[tuple] = set()

    for row_number, raw in enumerate(records, start=1):
        result.received += 1
        raw_text = json.dumps(raw, ensure_ascii=False, default=str)[:500]

        def reject(reason: str, order_id: str = "") -> None:
            result.rejected.append(Rejection(row_number, order_id, reason, raw_text))

        if not isinstance(raw, dict):
            reject("Record is not a JSON object")
            continue

        get = lambda name: raw.get(field_map[name])  # noqa: E731
        order_id = "" if _is_blank(get("order_id")) else str(get("order_id")).strip()

        missing = [field_map[f] for f in REQUIRED_FIELDS if _is_blank(get(f))]
        if missing:
            reject(f"Missing required field(s): {', '.join(missing)}", order_id)
            continue

        order_date = parse_date(get("order_date"))
        if order_date is None:
            reject(f"Unreadable date: {get('order_date')!r}", order_id)
            continue
        if order_date > today:
            reject(f"Order date {order_date} is in the future", order_id)
            continue

        quantity = parse_decimal(get("quantity"))
        if quantity is None:
            reject(f"Quantity is not a number: {get('quantity')!r}", order_id)
            continue
        if quantity <= 0:
            reject(f"Quantity must be greater than 0, got {quantity}", order_id)
            continue

        unit_price = parse_decimal(get("unit_price"))
        if unit_price is None:
            reject(f"Unit price is not a number: {get('unit_price')!r}", order_id)
            continue
        if unit_price < 0:
            reject(f"Unit price is negative: {unit_price}", order_id)
            continue

        currency = None if _is_blank(get("currency")) else str(get("currency")).strip().upper()
        if expected_currency and currency and currency != expected_currency:
            reject(f"Currency {currency} does not match report currency {expected_currency}",
                   order_id)
            continue

        line_id = get("line_id")
        if _is_blank(line_id):
            # Without a line id, an identical record is treated as a duplicate.
            dedup_key = ("content", json.dumps(raw, sort_keys=True, default=str))
        else:
            dedup_key = ("line", order_id, str(line_id).strip())
        if dedup_key in seen_keys:
            reject("Duplicate record", order_id)
            continue
        seen_keys.add(dedup_key)

        # Out-of-range dates are expected, not errors: skip them without logging.
        if (date_from and order_date < date_from) or (date_to and order_date > date_to):
            result.out_of_period += 1
            continue

        customer = get("customer_id")
        result.clean.append(CleanRecord(
            order_id=order_id,
            order_date=order_date,
            quantity=quantity,
            unit_price=unit_price,
            customer_id=None if _is_blank(customer) else str(customer).strip(),
            currency=currency,
        ))

    currencies = {r.currency for r in result.clean if r.currency}
    if len(currencies) > 1:
        raise FatalError(
            f"Records contain several currencies ({', '.join(sorted(currencies))}). "
            "Totals across currencies would be wrong. Rerun with --currency XXX.")
    return result


# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #

def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def compute_kpis(result: ValidationResult) -> list[tuple[str, Any, str]]:
    """Return (label, value, number_format) rows for the KPI sheet."""
    clean = result.clean
    revenue = sum((r.revenue for r in clean), Decimal(0))
    units = sum((r.quantity for r in clean), Decimal(0))
    orders = len({r.order_id for r in clean})
    customers = {r.customer_id for r in clean if r.customer_id}
    currency = next((r.currency for r in clean if r.currency), None)

    rows: list[tuple[str, Any, str]] = [
        ("Period start", min((r.order_date for r in clean), default=None), "yyyy-mm-dd"),
        ("Period end", max((r.order_date for r in clean), default=None), "yyyy-mm-dd"),
        ("Currency", currency or "not provided", "@"),
        ("Total revenue", money(revenue), "#,##0.00"),
        ("Number of orders", orders, "#,##0"),
        ("Units sold", units, "#,##0.##"),
        ("Average order value", money(revenue / orders) if orders else None, "#,##0.00"),
        ("Average price per unit", money(revenue / units) if units else None, "#,##0.00"),
        ("Average units per order", (units / orders).quantize(CENT) if orders else None,
         "#,##0.00"),
    ]
    if customers:
        rows.append(("Distinct customers", len(customers), "#,##0"))
        rows.append(("Revenue per customer", money(revenue / len(customers)), "#,##0.00"))
    rows += [
        ("Records received", result.received, "#,##0"),
        ("Records outside date range", result.out_of_period, "#,##0"),
        ("Records used", len(clean), "#,##0"),
        ("Records excluded (see Data Quality)", len(result.rejected), "#,##0"),
        ("Excluded share", result.excluded_share, "0.0%"),
    ]
    return rows


# --------------------------------------------------------------------------- #
# Excel output
# --------------------------------------------------------------------------- #

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WATERMARK_FONT = Font(italic=True, color="808080", size=9)


def _write_watermark(ws, generated_at: str, source: str) -> None:
    ws["A1"] = f"{WATERMARK} | {generated_at} | Source: {source}"
    ws["A1"].font = WATERMARK_FONT
    ws.oddHeader.center.text = WATERMARK
    ws.oddFooter.center.text = f"{WATERMARK} | {generated_at} | Page &P of &N"


def _write_table(ws, start_row: int, headers: list[str], rows: list[list[Any]],
                 formats: list[str] | None = None) -> None:
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=col, value=title)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for r, row in enumerate(rows, start=start_row + 1):
        for c, value in enumerate(row, start=1):
            if isinstance(value, Decimal):
                value = float(value)  # Excel stores numbers as doubles anyway.
            cell = ws.cell(row=r, column=c, value=value)
            if formats and formats[c - 1]:
                cell.number_format = formats[c - 1]
            cell.alignment = Alignment(vertical="top", wrap_text=(c == len(row) and c > 2))
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    for col in range(1, len(headers) + 1):
        letter = get_column_letter(col)
        longest = max((len(str(ws.cell(row=r, column=col).value or ""))
                       for r in range(start_row, start_row + len(rows) + 1)), default=10)
        ws.column_dimensions[letter].width = min(max(longest + 2, 12), 80)


def write_report(path: Path, result: ValidationResult, source: str) -> None:
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    wb = Workbook()

    ws = wb.active
    ws.title = "KPI Summary"
    _write_watermark(ws, generated_at, source)
    kpis = compute_kpis(result)
    ws.append([])
    start = 3
    for col, title in enumerate(("KPI", "Value"), start=1):
        cell = ws.cell(row=start, column=col, value=title)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for i, (label, value, fmt) in enumerate(kpis, start=start + 1):
        ws.cell(row=i, column=1, value=label).font = Font(bold=True)
        cell = ws.cell(row=i, column=2,
                       value=float(value) if isinstance(value, Decimal) else
                       ("n/a" if value is None else value))
        cell.number_format = fmt
        cell.alignment = Alignment(horizontal="right")
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 20

    dq = wb.create_sheet("Data Quality")
    _write_watermark(dq, generated_at, source)
    if result.rejected:
        _write_table(dq, 3, ["Record #", "Order ID", "Reason", "Raw record"],
                     [[r.row_number, r.order_id, r.reason, r.raw] for r in result.rejected])
    else:
        dq["A3"] = "All records passed validation. Nothing was excluded."

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_field_map(pairs: list[str]) -> dict[str, str]:
    mapping = dict(DEFAULT_FIELD_MAP)
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or key not in mapping or not value:
            raise FatalError(f"Invalid --map '{pair}'. Use one of "
                             f"{', '.join(mapping)} like order_date=createdAt.")
        mapping[key] = value
    return mapping


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="API endpoint that returns the sales records as JSON.")
    src.add_argument("--input-file", type=Path, help="Read a JSON export instead of the API.")
    p.add_argument("--out", type=Path, default=Path("sales_report.xlsx"),
                   help="Excel file to write (default: sales_report.xlsx).")
    p.add_argument("--token-env", default="SALES_API_TOKEN",
                   help="Environment variable holding the API token (default: SALES_API_TOKEN).")
    p.add_argument("--api-key-header",
                   help="Send the token in this header instead of 'Authorization: Bearer'.")
    p.add_argument("--records-path",
                   help="Dotted path to the list of records in the JSON, e.g. 'data.items'.")
    p.add_argument("--next-path",
                   help="Dotted path to the next page URL, e.g. 'links.next'. Omit if no paging.")
    p.add_argument("--map", action="append", default=[], metavar="FIELD=API_FIELD",
                   help="Map a field to the API's name, e.g. --map order_date=createdAt. "
                        "Repeatable.")
    p.add_argument("--currency", help="Report currency, e.g. EUR. Other currencies are excluded.")
    p.add_argument("--date-from", type=date.fromisoformat, help="First date to include (YYYY-MM-DD).")
    p.add_argument("--date-to", type=date.fromisoformat, help="Last date to include (YYYY-MM-DD).")
    p.add_argument("--max-excluded-share", type=float, default=0.05,
                   help="Exit with code 2 if more than this share of records is excluded "
                        "(default: 0.05 = 5%%). The report is still written.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        field_map = parse_field_map(args.map)
        if args.input_file:
            records = load_records_from_file(args.input_file, args.records_path)
            source = str(args.input_file)
        else:
            token = os.environ.get(args.token_env)
            records = fetch_records(args.url, token, args.api_key_header,
                                    args.records_path, args.next_path)
            source = args.url
        if not records:
            raise FatalError("The source returned no records; no report was written.")

        currency = args.currency.upper() if args.currency else None
        result = validate(records, field_map, currency, args.date_from, args.date_to)
        if not result.clean:
            raise FatalError(f"None of the {result.received} records passed validation. "
                             "Check --map and --records-path.")
        write_report(args.out, result, source)
    except FatalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FATAL

    share = result.excluded_share
    print(f"Report written to {args.out}: {len(result.clean)} records used, "
          f"{len(result.rejected)} excluded ({share:.1%}).")
    if share > args.max_excluded_share:
        print(f"WARNING: excluded share {share:.1%} is above the limit of "
              f"{args.max_excluded_share:.1%}. See the 'Data Quality' sheet.", file=sys.stderr)
        return EXIT_QUALITY_THRESHOLD
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
