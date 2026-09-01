"""CSV ingestion for orders.csv / payments.csv.

Column names are matched dynamically against a list of accepted aliases per
logical field (see ORDER_FIELD_ALIASES / PAYMENT_FIELD_ALIASES below), not a
single hardcoded name -- real-world exports name the same thing differently
("amount" vs "total" vs "order_total" vs "price"). Matching is
case/whitespace/punctuation-insensitive: "Order ID", "order-id", and
"OrderId" all resolve to the same logical field. The first alias in a
field's list that's present in the file wins, so list your preferred/most
specific name first.

Normalization performed here (kept intentionally conservative -- we only
clean formatting, we never change what a value *means*):

  * column names are matched via the alias lists above
  * string values are stripped of surrounding whitespace
  * amount is parsed into a Decimal (handles "$", ",", surrounding spaces,
    and accounting-style parentheses for negatives)
  * currency is upper-cased (e.g. "usd" -> "USD")
  * order_id / payment_id are kept as strings (never coerced to int) and
    stripped, since IDs are opaque identifiers, not numbers
  * status is lower-cased for consistent comparisons
  * blank/whitespace-only rows are skipped
  * the original row is kept under "raw" on every parsed record for audit

Rows that are missing a required field (order_id/amount for orders,
payment_id/order_id/amount for payments) are skipped and logged rather
than silently guessed at.
"""

import csv
import io
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any


class CSVParseError(Exception):
    def __init__(self, message: str, row_errors: list[str] | None = None):
        super().__init__(message)
        self.row_errors = row_errors or []


# Logical field -> accepted column-name aliases, most-preferred first.
# Add more aliases here as real-world exports turn up new names -- this is
# the only place that needs to change.
ORDER_FIELD_ALIASES: dict[str, list[str]] = {
    "order_id": ["order_id", "orderid", "order_number", "order_no", "order_ref", "id", "order"],
    "amount": ["amount", "order_amount", "order_total", "total_amount", "total", "grand_total", "price"],
    "customer_name": ["customer_name", "customer", "client_name", "buyer", "buyer_name", "name"],
    "order_date": ["order_date", "date", "created_at", "created_date", "order_created"],
    "currency": ["currency", "currency_code", "curr"],
    "status": ["status", "order_status", "state"],
}
PAYMENT_FIELD_ALIASES: dict[str, list[str]] = {
    "payment_id": ["payment_id", "paymentid", "payment_number", "transaction_id", "txn_id", "charge_id", "id"],
    "order_id": ["order_id", "orderid", "order_number", "order_no", "order_ref", "reference_id", "reference", "order"],
    "amount": ["amount", "payment_amount", "charge_amount", "amount_paid", "paid_amount", "total"],
    "payment_date": ["payment_date", "date", "processed_at", "charged_at", "created_at"],
    "currency": ["currency", "currency_code", "curr"],
    "status": ["status", "payment_status", "state"],
}

ORDERS_REQUIRED = ("order_id", "amount")
PAYMENTS_REQUIRED = ("payment_id", "order_id", "amount")


def _normalize(name: str) -> str:
    """'Order ID', 'order-id', 'OrderId ' all become 'order_id'."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _resolve_columns(fieldnames: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    """Returns {logical_field: original_csv_header} for every logical field
    whose alias list matches one of the file's actual headers."""
    normalized_to_original = {_normalize(name): name for name in fieldnames if name}
    resolved: dict[str, str] = {}
    for field, candidates in aliases.items():
        for candidate in candidates:
            if candidate in normalized_to_original:
                resolved[field] = normalized_to_original[candidate]
                break
    return resolved


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


def _get(row: dict, columns: dict[str, str], field: str) -> str:
    original_header = columns.get(field)
    if original_header is None:
        return ""
    value = row.get(original_header)
    return value.strip() if isinstance(value, str) else ""


def parse_orders_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    rows, fieldnames = _read_rows(file_bytes)
    columns = _resolve_columns(fieldnames, ORDER_FIELD_ALIASES)
    missing = [f for f in ORDERS_REQUIRED if f not in columns]
    if missing:
        raise CSVParseError(
            f"orders.csv is missing required column(s): {', '.join(missing)} "
            f"(found columns: {', '.join(fieldnames)})"
        )

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):  # start=2: header is line 1
        order_id = _get(row, columns, "order_id")
        amount_raw = _get(row, columns, "amount")
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
            "customer_name": _get(row, columns, "customer_name") or None,
            "order_date": _get(row, columns, "order_date") or None,
            "amount": amount,
            "currency": (_get(row, columns, "currency") or "USD").upper(),
            "status": (_get(row, columns, "status") or "").lower() or None,
            "raw": row,
        })

    # Row-level problems (bad amount, missing field) are non-fatal: we skip
    # the bad row, log why, and keep going rather than failing the whole upload.
    for err in errors:
        logging.warning(err)
    return records


def parse_payments_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    rows, fieldnames = _read_rows(file_bytes)
    columns = _resolve_columns(fieldnames, PAYMENT_FIELD_ALIASES)
    missing = [f for f in PAYMENTS_REQUIRED if f not in columns]
    if missing:
        raise CSVParseError(
            f"payments.csv is missing required column(s): {', '.join(missing)} "
            f"(found columns: {', '.join(fieldnames)})"
        )

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):
        payment_id = _get(row, columns, "payment_id")
        order_id = _get(row, columns, "order_id")
        amount_raw = _get(row, columns, "amount")
        if not payment_id or not order_id or not amount_raw:
            if any(v and v.strip() for v in row.values()):
                errors.append(f"payments.csv line {i}: missing payment_id, order_id, or amount, row skipped")
            continue
        try:
            amount = _parse_amount(amount_raw)
        except InvalidOperation:
            errors.append(f"payments.csv line {i}: could not parse amount '{amount_raw}', row skipped")
            continue

        records.append({
            "payment_id": payment_id,
            "order_id": order_id,
            "payment_date": _get(row, columns, "payment_date") or None,
            "amount": amount,
            "currency": (_get(row, columns, "currency") or "USD").upper(),
            "status": (_get(row, columns, "status") or "").lower() or None,
            "raw": row,
        })

    for err in errors:
        logging.warning(err)
    return records
