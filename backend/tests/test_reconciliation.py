"""Tests for the deterministic reconciliation engine (reconciliation.py).

These operate purely on in-memory order/payment dicts -- no database, no
network -- so they are fast and fully deterministic, exactly matching what
reconcile() actually receives at runtime after csv_parser.py normalizes a
CSV row.
"""

from decimal import Decimal

from models import DiscrepancyCategory, Priority
from reconciliation import reconcile, summarize


def order(order_id, amount, currency="USD", status="paid", **kw):
    return {
        "order_id": order_id, "customer_name": "Test Customer", "order_date": "2026-08-01",
        "amount": Decimal(amount), "currency": currency, "status": status, "raw": {}, **kw,
    }


def payment(payment_id, order_id, amount, currency="USD", status="succeeded", **kw):
    return {
        "payment_id": payment_id, "order_id": order_id, "payment_date": "2026-08-01",
        "amount": Decimal(amount), "currency": currency, "status": status, "raw": {}, **kw,
    }


def _category_for(results, order_id):
    matches = [r for r in results if r["order_id"] == order_id]
    assert len(matches) == 1, f"expected exactly one result for {order_id}, got {len(matches)}"
    return matches[0]


def test_exact_match():
    results = reconcile([order("A1", "100.00")], [payment("P1", "A1", "100.00")])
    r = _category_for(results, "A1")
    assert r["category"] == DiscrepancyCategory.MATCHED
    assert r["priority"] == Priority.NONE
    assert r["financial_impact"] == 0.0


def test_amount_mismatch():
    results = reconcile([order("A2", "100.00")], [payment("P2", "A2", "75.00")])
    r = _category_for(results, "A2")
    assert r["category"] == DiscrepancyCategory.AMOUNT_MISMATCH
    assert r["difference"] == 25.0
    assert r["financial_impact"] == 25.0
    assert r["priority"] == Priority.MEDIUM  # 25 >= 10, < 100


def test_missing_payment():
    results = reconcile([order("A3", "50.00")], [])
    r = _category_for(results, "A3")
    assert r["category"] == DiscrepancyCategory.MISSING_PAYMENT
    assert r["payment_id"] is None
    assert r["financial_impact"] == 50.0


def test_unknown_payment():
    results = reconcile([], [payment("P4", "A4", "20.00")])
    r = _category_for(results, "A4")
    assert r["category"] == DiscrepancyCategory.UNKNOWN_PAYMENT
    assert r["order_amount"] is None
    assert r["financial_impact"] == 20.0


def test_duplicate_order():
    orders = [order("A5", "40.00"), order("A5", "40.00")]
    results = reconcile(orders, [payment("P5", "A5", "40.00")])
    r = _category_for(results, "A5")
    assert r["category"] == DiscrepancyCategory.DUPLICATE_ORDER
    # impact = the extra order's amount (one order beyond the first)
    assert r["financial_impact"] == 40.0


def test_duplicate_payment():
    payments = [payment("P6a", "A6", "30.00"), payment("P6b", "A6", "30.00")]
    results = reconcile([order("A6", "30.00")], payments)
    r = _category_for(results, "A6")
    assert r["category"] == DiscrepancyCategory.DUPLICATE_PAYMENT
    assert r["financial_impact"] == 30.0


def test_currency_mismatch():
    results = reconcile([order("A7", "65.00", currency="EUR")], [payment("P7", "A7", "65.00", currency="USD")])
    r = _category_for(results, "A7")
    assert r["category"] == DiscrepancyCategory.CURRENCY_MISMATCH


def test_rounding_difference_within_tolerance():
    results = reconcile([order("A8", "49.99")], [payment("P8", "A8", "50.00")])
    r = _category_for(results, "A8")
    assert r["category"] == DiscrepancyCategory.ROUNDING_DIFFERENCE
    assert r["financial_impact"] == 0.0  # immaterial by definition
    assert r["priority"] == Priority.LOW


def test_amount_mismatch_just_above_tolerance():
    results = reconcile([order("A9", "49.98")], [payment("P9", "A9", "50.00")])
    r = _category_for(results, "A9")
    assert r["category"] == DiscrepancyCategory.AMOUNT_MISMATCH


def test_refund_charge_issue():
    results = reconcile(
        [order("A10", "220.00", status="paid")],
        [payment("P10", "A10", "220.00", status="refunded")],
    )
    r = _category_for(results, "A10")
    assert r["category"] == DiscrepancyCategory.REFUND_CHARGE_ISSUE
    assert r["financial_impact"] == 220.0


def test_refund_acknowledged_by_order_is_not_a_discrepancy():
    """If the order itself is marked refunded/cancelled, a refunded
    payment is expected, not a discrepancy -- both sides agree."""
    results = reconcile(
        [order("A11", "80.00", status="refunded")],
        [payment("P11", "A11", "80.00", status="refunded")],
    )
    r = _category_for(results, "A11")
    assert r["category"] == DiscrepancyCategory.MATCHED


def test_duplicate_detection_takes_priority_over_amount_mismatch():
    """A duplicate order with a mismatched payment amount is still
    classified as DUPLICATE_ORDER first -- duplicates are evaluated before
    any amount comparison happens."""
    orders = [order("A12", "40.00"), order("A12", "40.00")]
    results = reconcile(orders, [payment("P12", "A12", "999.00")])
    r = _category_for(results, "A12")
    assert r["category"] == DiscrepancyCategory.DUPLICATE_ORDER


def test_priority_thresholds():
    results = reconcile([order("B1", "1000.00")], [payment("Q1", "B1", "0.00")])
    assert _category_for(results, "B1")["priority"] == Priority.CRITICAL

    results = reconcile([order("B2", "150.00")], [payment("Q2", "B2", "0.00")])
    assert _category_for(results, "B2")["priority"] == Priority.HIGH

    results = reconcile([order("B3", "5.00")], [payment("Q3", "B3", "0.00")])
    assert _category_for(results, "B3")["priority"] == Priority.LOW


def test_summarize_does_not_double_count_money_at_risk():
    orders = [order("C1", "100.00"), order("C2", "50.00")]
    payments = [payment("R1", "C1", "70.00")]  # C2 has no payment
    results = reconcile(orders, payments)
    summary = summarize(results)
    # C1: AMOUNT_MISMATCH impact 30, C2: MISSING_PAYMENT impact 50
    assert summary["money_at_risk"] == 80.0
    assert summary["discrepancy_count"] == 2
    assert summary["matched_count"] == 0


def test_reconcile_is_deterministic_across_runs():
    orders = [order("D1", "10.00"), order("D2", "20.00")]
    payments = [payment("S1", "D1", "10.00"), payment("S2", "D2", "25.00")]
    first = reconcile(orders, payments)
    second = reconcile(orders, payments)
    assert first == second
