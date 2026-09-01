from decimal import Decimal

import pytest

from csv_parser import CSVParseError, parse_orders_csv, parse_payments_csv


def test_parses_clean_orders_csv():
    csv_bytes = b"order_id,customer_name,order_date,amount,currency,status\nORD-1,Jane,2026-08-01,100.00,USD,paid\n"
    records = parse_orders_csv(csv_bytes)
    assert len(records) == 1
    assert records[0]["order_id"] == "ORD-1"
    assert records[0]["amount"] == Decimal("100.00")
    assert records[0]["currency"] == "USD"


def test_normalizes_whitespace_case_and_currency_formatting():
    csv_bytes = (
        b"Order_ID , customer_name, order_date, Amount, Currency, Status\n"
        b' ORD-2 , Jane , 2026-08-01,"$1,250.00", usd , PAID\n'
    )
    records = parse_orders_csv(csv_bytes)
    r = records[0]
    assert r["order_id"] == "ORD-2"
    assert r["amount"] == Decimal("1250.00")
    assert r["currency"] == "USD"
    assert r["status"] == "paid"


def test_missing_required_column_raises():
    csv_bytes = b"customer_name,amount\nJane,100.00\n"
    with pytest.raises(CSVParseError):
        parse_orders_csv(csv_bytes)


def test_row_with_missing_amount_is_skipped_not_crashed():
    csv_bytes = b"order_id,amount\nORD-1,100.00\nORD-2,\n"
    records = parse_orders_csv(csv_bytes)
    assert len(records) == 1
    assert records[0]["order_id"] == "ORD-1"


def test_row_with_unparseable_amount_is_skipped():
    csv_bytes = b"order_id,amount\nORD-1,not-a-number\nORD-2,50.00\n"
    records = parse_orders_csv(csv_bytes)
    assert len(records) == 1
    assert records[0]["order_id"] == "ORD-2"


def test_parses_payments_csv_with_order_reference():
    csv_bytes = b"payment_id,order_id,amount,currency,status\nPAY-1,ORD-1,100.00,USD,succeeded\n"
    records = parse_payments_csv(csv_bytes)
    assert records[0]["payment_id"] == "PAY-1"
    assert records[0]["order_id"] == "ORD-1"
    assert records[0]["amount"] == Decimal("100.00")


def test_defaults_missing_currency_to_usd():
    csv_bytes = b"order_id,amount\nORD-1,10.00\n"
    records = parse_orders_csv(csv_bytes)
    assert records[0]["currency"] == "USD"


def test_accepts_common_column_name_aliases_for_orders():
    csv_bytes = b"Order Number,Total,Buyer\nORD-1,99.00,Jane\n"
    records = parse_orders_csv(csv_bytes)
    assert records[0]["order_id"] == "ORD-1"
    assert records[0]["amount"] == Decimal("99.00")
    assert records[0]["customer_name"] == "Jane"


def test_accepts_common_column_name_aliases_for_payments():
    csv_bytes = b"Transaction ID,Reference,Amount Paid\nPAY-1,ORD-1,50.00\n"
    records = parse_payments_csv(csv_bytes)
    assert records[0]["payment_id"] == "PAY-1"
    assert records[0]["order_id"] == "ORD-1"
    assert records[0]["amount"] == Decimal("50.00")


def test_still_reports_missing_column_when_no_alias_matches():
    csv_bytes = b"customer_name,notes\nJane,hello\n"
    with pytest.raises(CSVParseError):
        parse_orders_csv(csv_bytes)
