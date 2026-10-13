import json
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sales_report as sr  # noqa: E402

TODAY = date(2026, 10, 13)


def rec(**overrides):
    base = {"order_id": "A1", "line_id": 1, "order_date": "2026-09-01",
            "quantity": 2, "unit_price": "10.00", "customer_id": "C1", "currency": "EUR"}
    base.update(overrides)
    return base


class ValidateTests(unittest.TestCase):
    def run_validate(self, records, **kw):
        return sr.validate(records, sr.DEFAULT_FIELD_MAP, today=TODAY, **kw)

    def test_valid_record_is_kept(self):
        result = self.run_validate([rec()])
        self.assertEqual(len(result.clean), 1)
        self.assertEqual(result.clean[0].revenue, Decimal("20.00"))

    def test_each_rule_rejects_with_reason(self):
        cases = {
            "Missing required field": rec(order_id=None),
            "Unreadable date": rec(order_date="31/31/2026"),
            "in the future": rec(order_date="2027-01-01"),
            "Quantity must be greater than 0": rec(quantity=0),
            "Quantity is not a number": rec(quantity="two"),
            "Unit price is negative": rec(unit_price=-1),
            "Unit price is not a number": rec(unit_price="abc"),
        }
        for reason, record in cases.items():
            with self.subTest(reason=reason):
                result = self.run_validate([record])
                self.assertEqual(result.clean, [])
                self.assertIn(reason, result.rejected[0].reason)

    def test_duplicate_line_is_rejected(self):
        result = self.run_validate([rec(), rec()])
        self.assertEqual(len(result.clean), 1)
        self.assertEqual(result.rejected[0].reason, "Duplicate record")

    def test_duplicate_without_line_id_uses_content(self):
        result = self.run_validate([rec(line_id=None), rec(line_id=None),
                                    rec(line_id=None, quantity=5)])
        self.assertEqual(len(result.clean), 2)
        self.assertEqual(len(result.rejected), 1)

    def test_mixed_currencies_without_filter_is_fatal(self):
        with self.assertRaises(sr.FatalError):
            self.run_validate([rec(), rec(line_id=2, currency="USD")])

    def test_currency_filter_excludes_other_currencies(self):
        result = self.run_validate([rec(), rec(line_id=2, currency="USD")],
                                   expected_currency="EUR")
        self.assertEqual(len(result.clean), 1)
        self.assertIn("USD", result.rejected[0].reason)

    def test_date_range_skips_without_counting_as_error(self):
        result = self.run_validate([rec(), rec(line_id=2, order_date="2026-08-01")],
                                   date_from=date(2026, 9, 1))
        self.assertEqual(len(result.clean), 1)
        self.assertEqual(result.rejected, [])
        self.assertEqual(result.out_of_period, 1)

    def test_field_mapping(self):
        mapping = sr.parse_field_map(["order_date=createdAt", "unit_price=price"])
        raw = {"order_id": "X", "createdAt": "2026-09-01", "quantity": 1, "price": 3}
        result = sr.validate([raw], mapping, today=TODAY)
        self.assertEqual(result.clean[0].unit_price, Decimal(3))

    def test_bad_field_mapping_is_fatal(self):
        with self.assertRaises(sr.FatalError):
            sr.parse_field_map(["nonsense=x"])


class KpiTests(unittest.TestCase):
    def test_kpis_are_exact(self):
        records = [rec(order_id="A1", line_id=1, quantity=2, unit_price="19.99"),
                   rec(order_id="A1", line_id=2, quantity=1, unit_price="5.00"),
                   rec(order_id="A2", line_id=1, quantity=3, unit_price="12.50",
                       customer_id="C2", order_date="2026-09-10")]
        result = sr.validate(records, sr.DEFAULT_FIELD_MAP, today=TODAY)
        kpis = {label: value for label, value, _ in sr.compute_kpis(result)}
        self.assertEqual(kpis["Total revenue"], Decimal("82.48"))
        self.assertEqual(kpis["Number of orders"], 2)
        self.assertEqual(kpis["Units sold"], Decimal(6))
        self.assertEqual(kpis["Average order value"], Decimal("41.24"))
        self.assertEqual(kpis["Average price per unit"], Decimal("13.75"))
        self.assertEqual(kpis["Distinct customers"], 2)
        self.assertEqual(kpis["Period start"], date(2026, 9, 1))
        self.assertEqual(kpis["Period end"], date(2026, 9, 10))


class EndToEndTests(unittest.TestCase):
    def test_sample_file_produces_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.xlsx"
            code = sr.main(["--input-file", str(ROOT / "sample_data" / "sales.json"),
                            "--records-path", "data.items", "--currency", "EUR",
                            "--out", str(out)])
            # The sample deliberately contains bad rows, so the quality limit trips.
            self.assertEqual(code, sr.EXIT_QUALITY_THRESHOLD)
            wb = load_workbook(out)
            self.assertEqual(wb.sheetnames, ["KPI Summary", "Data Quality"])
            kpi = {row[0]: row[1] for row in wb["KPI Summary"].iter_rows(min_row=4, values_only=True)}
            self.assertAlmostEqual(kpi["Total revenue"], 182.38)
            self.assertEqual(kpi["Number of orders"], 3)
            self.assertEqual(kpi["Records excluded (see Data Quality)"], 5)
            self.assertIn(sr.WATERMARK, wb["KPI Summary"]["A1"].value)
            self.assertIn(sr.WATERMARK, wb["Data Quality"]["A1"].value)

    def test_api_pagination_and_auth_header(self):
        pages = {
            "https://api/sales": {"items": [rec()], "next": "https://api/sales?p=2"},
            "https://api/sales?p=2": {"items": [rec(line_id=2)], "next": None},
        }
        calls = []

        def fake_get(url, headers, timeout):
            calls.append(headers)
            resp = mock.Mock(status_code=200)
            resp.json.return_value = pages[url]
            return resp

        with mock.patch.object(sr.requests, "get", side_effect=fake_get):
            records = sr.fetch_records("https://api/sales", "tok", None, "items", "next")
        self.assertEqual(len(records), 2)
        self.assertEqual(calls[0]["Authorization"], "Bearer tok")

    def test_unauthorized_is_fatal(self):
        resp = mock.Mock(status_code=401)
        with mock.patch.object(sr.requests, "get", return_value=resp):
            with self.assertRaises(sr.FatalError):
                sr.fetch_records("https://api/sales", "bad", None, None, None)

    def test_no_valid_records_is_fatal_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            src.write_text(json.dumps([{"foo": 1}]))
            out = Path(tmp) / "report.xlsx"
            self.assertEqual(sr.main(["--input-file", str(src), "--out", str(out)]),
                             sr.EXIT_FATAL)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
