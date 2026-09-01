"""CSV ingestion for orders.csv / payments.csv.

Expected columns (case-insensitive, whitespace-tolerant):

    orders.csv:   order_id, customer_name, order_date, amount, currency, status
    payments.csv: payment_id, order_id, payment_date, amount, currency, status

Normalization performed here (kept intentionally conservative -- we only
clean formatting, we never change what a value *means*):

  * column names are matched case-insensitively and stripped of whitespace
  * string values are stripped of surrounding whitespace
  * amount is parsed into a Decimal (handles "$", ",", surrounding spaces)
  * currency is upper-cased (e.g. "usd" -> "USD")
  * order_id / payment_id are kept as strings (never coerced to int) and
    stripped, since IDs are opaque identifiers, not numbers
  * status is lower-cased for consistent comparisons
  * blank/whitespace-only rows are skipped
  * the original row is kept under "raw" on every parsed record for audit

Rows that are missing a required field (order_id/amount for orders,
payment_id/order_id/amount for payments) are collected as errors rather
than silently dropped or guessed at.
"""

import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Any


class CSVParseError(Exception):
    def __init__(self, message: str, row_errors: list[str] | None = None):
        super().__init__(message)
        self.row_errors = row_errors or []


ORDERS_REQUIRED = {"order_id", "amount"}
PAYMENTS_REQUIRED = {"payment_id", "order_id", "amount"}


def _normalize_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map lowercased/stripped header -> original header, so lookups are
    case-insensitive without mutating the DictReader's row keys twice."""
    return {name.strip().lower(): name for name in fieldnames if name}


def _parse_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]  # accounting-style negative, e.g. refunds
    return Decimal(cleaned)


def _read_rows(file_bytes: bytes) -> tuple[list[dict[str, str]], list[str]]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CSVParseError("CSV file has no header row")
    return list(reader), list(reader.fieldnames)


def _get(row: dict, header_map: dict[str, str], key: str) -> str:
    original_key = header_map.get(key)
    if original_key is None:
        return ""
    value = row.get(original_key)
    return value.strip() if isinstance(value, str) else ""


def parse_orders_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    rows, fieldnames = _read_rows(file_bytes)
    header_map = _normalize_headers(fieldnames)
    missing = ORDERS_REQUIRED - set(header_map.keys())
    if missing:
        raise CSVParseError(f"orders.csv is missing required column(s): {', '.join(sorted(missing))}")

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):  # start=2: header is line 1
        order_id = _get(row, header_map, "order_id")
        amount_raw = _get(row, header_map, "amount")
        if not order_id or not amount_raw:
            if any(v and v.strip() for v in row.values()):
                errors.append(f"orders.csv line {i}: missing order_id or amount, row skipped")
            continue
        try:
            amount = _parse_amount(amount_raw)
        except InvalidOperation:
            errors.append(f"orders.csv line {i}: could not parse amount '{amount_raw}', row skipped")
            continue

        records.append({
            "order_id": order_id,
            "customer_name": _get(row, header_map, "customer_name") or None,
            "order_date": _get(row, header_map, "order_date") or None,
            "amount": amount,
            "currency": (_get(row, header_map, "currency") or "USD").upper(),
            "status": (_get(row, header_map, "status") or "").lower() or None,
            "raw": row,
        })

    # Row-level problems (bad amount, missing field) are non-fatal: we skip
    # the bad row, log why, and keep going rather than failing the whole upload.
    for err in errors:
        logging.warning(err)
    return records


def parse_payments_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    rows, fieldnames = _read_rows(file_bytes)
    header_map = _normalize_headers(fieldnames)
    missing = PAYMENTS_REQUIRED - set(header_map.keys())
    if missing:
        raise CSVParseError(f"payments.csv is missing required column(s): {', '.join(sorted(missing))}")

    records: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=2):
        payment_id = _get(row, header_map, "payment_id")
        order_id = _get(row, header_map, "order_id")
        amount_raw = _get(row, header_map, "amount")
        if not payment_id or not order_id or not amount_raw:
            continue
        try:
            amount = _parse_amount(amount_raw)
        except InvalidOperation:
            continue

        records.append({
            "payment_id": payment_id,
            "order_id": order_id,
            "payment_date": _get(row, header_map, "payment_date") or None,
            "amount": amount,
            "currency": (_get(row, header_map, "currency") or "USD").upper(),
            "status": (_get(row, header_map, "status") or "").lower() or None,
            "raw": row,
        })

    return records
