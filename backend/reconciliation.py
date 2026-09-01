"""The deterministic reconciliation engine.

This module never calls an LLM and never guesses -- it is a pure function
of the parsed orders/payments records. Given the same input it always
produces the same output, which is what makes it testable and auditable.

MATCHING STRATEGY
------------------
order_id is the only reliable shared identifier between orders.csv and
payments.csv (payments.csv references the order it was collected for), so
it is the sole join key. Records are grouped by order_id and classified
using this priority (first applicable rule wins -- see README for the
full rationale):

  1. DUPLICATE_ORDER    -- order_id appears more than once in orders.csv
  2. DUPLICATE_PAYMENT  -- order_id has more than one payment row
  3. MISSING_PAYMENT    -- an order has zero matching payments
  4. UNKNOWN_PAYMENT    -- a payment's order_id matches no order
  5. REFUND_CHARGE_ISSUE-- payment is refunded but the order was never
                            marked as refunded/cancelled (books disagree)
  6. CURRENCY_MISMATCH  -- order and payment currencies differ
  7. AMOUNT_MISMATCH    -- |order.amount - payment.amount| > tolerance
  8. ROUNDING_DIFFERENCE-- 0 < |difference| <= tolerance
  9. MATCHED            -- everything lines up

Duplicates are checked first because a duplicate is a data-integrity
problem regardless of whether amounts happen to match -- classifying it
as anything else would hide the real issue.

Each order_id is classified into exactly one category, so every dollar of
financial impact is counted once. This is what prevents double-counting
in the money-at-risk total (see money_at_risk below).

TOLERANCE
---------
ROUNDING_TOLERANCE = 0.01 (one cent). Card processors and currency
conversions routinely produce sub-cent rounding; a 1-cent tolerance
absorbs that noise without hiding genuine mismatches. All money math uses
Decimal, never float, to avoid binary floating-point rounding artifacts.
"""

from decimal import Decimal
from typing import Any, Optional

from models import DiscrepancyCategory, Priority

ROUNDING_TOLERANCE = Decimal("0.01")

# Financial-impact thresholds used to assign a priority. Chosen so that a
# handful of large-dollar issues don't get lost in a sea of small ones --
# thresholds are in the same currency units as the amounts in the CSV.
_PRIORITY_THRESHOLDS: list[tuple[Decimal, Priority]] = [
    (Decimal("500"), Priority.CRITICAL),
    (Decimal("100"), Priority.HIGH),
    (Decimal("10"), Priority.MEDIUM),
]

# Statuses on the order side that indicate the business already knows the
# sale was reversed. If the order carries one of these, a refunded payment
# is NOT a discrepancy -- both sides agree.
_ORDER_REFUND_ACKNOWLEDGED_STATUSES = {"refunded", "cancelled", "canceled"}


def _priority_for_impact(impact: Decimal) -> Priority:
    for threshold, priority in _PRIORITY_THRESHOLDS:
        if impact >= threshold:
            return priority
    return Priority.LOW


def _f(value: Decimal) -> float:
    return float(value)


def _discrepancy(
    *,
    order_id: Optional[str],
    order: Optional[dict],
    payment: Optional[dict],
    category: DiscrepancyCategory,
    reason: str,
    impact: Decimal,
    difference: Optional[Decimal] = None,
) -> dict[str, Any]:
    priority = Priority.NONE if category == DiscrepancyCategory.MATCHED else _priority_for_impact(impact)
    if category == DiscrepancyCategory.ROUNDING_DIFFERENCE:
        priority = Priority.LOW

    # Embedded copies for the detail view / storage: amount converted to
    # float since Decimal isn't natively BSON/JSON serializable, and this
    # copy is for display only (all matching math already happened above).
    order_display = {**order, "amount": _f(order["amount"])} if order else None
    payment_display = {**payment, "amount": _f(payment["amount"])} if payment else None

    return {
        "order_id": order_id,
        "payment_id": payment["payment_id"] if payment else None,
        "order": order_display,
        "payment": payment_display,
        "category": category,
        "priority": priority,
        "status": "OPEN" if category != DiscrepancyCategory.MATCHED else "RESOLVED",
        "order_amount": _f(order["amount"]) if order else None,
        "payment_amount": _f(payment["amount"]) if payment else None,
        "difference": _f(difference) if difference is not None else None,
        "order_currency": order["currency"] if order else None,
        "payment_currency": payment["currency"] if payment else None,
        "reason": reason,
        "financial_impact": _f(impact),
    }


def _group_by_order_id(records: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(r["order_id"], []).append(r)
    return groups


def reconcile(orders: list[dict], payments: list[dict]) -> list[dict[str, Any]]:
    """Returns one discrepancy record per order_id (MATCHED rows included --
    they're discrepancy rows with category=MATCHED, which keeps the output
    a single uniform list for storage/summary/pagination)."""
    orders_by_id = _group_by_order_id(orders)
    payments_by_id = _group_by_order_id(payments)

    all_order_ids = set(orders_by_id) | set(payments_by_id)
    results: list[dict[str, Any]] = []

    for order_id in sorted(all_order_ids):
        order_group = orders_by_id.get(order_id, [])
        payment_group = payments_by_id.get(order_id, [])

        # 1. Duplicate order
        if len(order_group) > 1:
            extra_total = sum((o["amount"] for o in order_group[1:]), Decimal("0"))
            results.append(_discrepancy(
                order_id=order_id, order=order_group[0], payment=payment_group[0] if payment_group else None,
                category=DiscrepancyCategory.DUPLICATE_ORDER,
                reason=f"order_id '{order_id}' appears {len(order_group)} times in orders.csv",
                impact=extra_total,
            ))
            continue

        # 2. Duplicate payment
        if len(payment_group) > 1:
            extra_total = sum((p["amount"] for p in payment_group[1:]), Decimal("0"))
            results.append(_discrepancy(
                order_id=order_id, order=order_group[0] if order_group else None, payment=payment_group[0],
                category=DiscrepancyCategory.DUPLICATE_PAYMENT,
                reason=f"order_id '{order_id}' has {len(payment_group)} payment records (possible double charge)",
                impact=extra_total,
            ))
            continue

        # 3. Missing payment
        if order_group and not payment_group:
            order = order_group[0]
            results.append(_discrepancy(
                order_id=order_id, order=order, payment=None,
                category=DiscrepancyCategory.MISSING_PAYMENT,
                reason="Order exists with no matching payment record",
                impact=order["amount"],
            ))
            continue

        # 4. Unknown payment
        if payment_group and not order_group:
            payment = payment_group[0]
            results.append(_discrepancy(
                order_id=order_id, order=None, payment=payment,
                category=DiscrepancyCategory.UNKNOWN_PAYMENT,
                reason="Payment references an order_id that does not exist in orders.csv",
                impact=payment["amount"],
            ))
            continue

        # Clean 1:1 pair from here on.
        order, payment = order_group[0], payment_group[0]

        # 5. Refund/charge conflict
        if payment["status"] == "refunded" and order["status"] not in _ORDER_REFUND_ACKNOWLEDGED_STATUSES:
            results.append(_discrepancy(
                order_id=order_id, order=order, payment=payment,
                category=DiscrepancyCategory.REFUND_CHARGE_ISSUE,
                reason="Payment was refunded but the order is not marked refunded/cancelled",
                impact=payment["amount"],
            ))
            continue

        # 6. Currency mismatch
        if order["currency"] != payment["currency"]:
            results.append(_discrepancy(
                order_id=order_id, order=order, payment=payment,
                category=DiscrepancyCategory.CURRENCY_MISMATCH,
                reason=f"Order currency {order['currency']} does not match payment currency {payment['currency']}",
                impact=order["amount"],
            ))
            continue

        # 7/8/9. Amount comparison
        difference = abs(order["amount"] - payment["amount"])
        if difference == 0:
            results.append(_discrepancy(
                order_id=order_id, order=order, payment=payment,
                category=DiscrepancyCategory.MATCHED,
                reason="Order total matches payment amount exactly",
                impact=Decimal("0"), difference=difference,
            ))
        elif difference <= ROUNDING_TOLERANCE:
            results.append(_discrepancy(
                order_id=order_id, order=order, payment=payment,
                category=DiscrepancyCategory.ROUNDING_DIFFERENCE,
                reason=f"Amounts differ by {difference}, within the {ROUNDING_TOLERANCE} rounding tolerance",
                impact=Decimal("0"), difference=difference,
            ))
        else:
            results.append(_discrepancy(
                order_id=order_id, order=order, payment=payment,
                category=DiscrepancyCategory.AMOUNT_MISMATCH,
                reason=f"Order total {order['amount']} does not match payment amount {payment['amount']}",
                impact=difference, difference=difference,
            ))

    return results


def summarize(discrepancies: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregates the discrepancy list into the dashboard summary numbers.

    matched_value    -- payment amount for rows classified MATCHED or
                         ROUNDING_DIFFERENCE (money that genuinely settled)
    disputed_value    -- order/payment amount involved in every other
                         category (how much revenue is "in question")
    money_at_risk     -- sum of financial_impact across those same rows
                         (the actual dollar exposure, always <= disputed_value
                         since e.g. an AMOUNT_MISMATCH disputes the full
                         order amount but only the difference is at risk)

    Because reconcile() emits exactly one row per order_id, these sums
    never double-count a single transaction.
    """
    total_order_value = Decimal("0")
    total_payment_value = Decimal("0")
    matched_value = Decimal("0")
    disputed_value = Decimal("0")
    money_at_risk = Decimal("0")
    matched_count = 0
    discrepancy_count = 0
    by_type: dict[str, dict[str, Decimal | int]] = {}
    by_priority: dict[str, int] = {}
    currency_breakdown: dict[str, int] = {}
    total_orders = 0
    total_payments = 0

    for d in discrepancies:
        category = d["category"]
        impact = Decimal(str(d["financial_impact"]))

        if d["order_amount"] is not None:
            total_order_value += Decimal(str(d["order_amount"]))
            total_orders += 1
        if d["payment_amount"] is not None:
            total_payment_value += Decimal(str(d["payment_amount"]))
            total_payments += 1

        currency = d["order_currency"] or d["payment_currency"] or "UNKNOWN"
        currency_breakdown[currency] = currency_breakdown.get(currency, 0) + 1

        entry = by_type.setdefault(category, {"count": 0, "impact": Decimal("0")})
        entry["count"] += 1
        entry["impact"] += impact

        priority = d["priority"]
        by_priority[priority] = by_priority.get(priority, 0) + 1

        if category in (DiscrepancyCategory.MATCHED, DiscrepancyCategory.ROUNDING_DIFFERENCE):
            matched_count += 1
            settled = d["payment_amount"] if d["payment_amount"] is not None else d["order_amount"]
            matched_value += Decimal(str(settled or 0))
        else:
            discrepancy_count += 1
            disputed_amount = d["order_amount"] if d["order_amount"] is not None else d["payment_amount"]
            disputed_value += Decimal(str(disputed_amount or 0))
            money_at_risk += impact

    return {
        "total_orders": total_orders,
        "total_payments": total_payments,
        "total_order_value": float(total_order_value),
        "total_payment_value": float(total_payment_value),
        "matched_value": float(matched_value),
        "disputed_value": float(disputed_value),
        "money_at_risk": float(money_at_risk),
        "matched_count": matched_count,
        "discrepancy_count": discrepancy_count,
        "discrepancies_by_type": [
            {"category": cat, "count": v["count"], "financial_impact": float(v["impact"])}
            for cat, v in sorted(by_type.items())
        ],
        "priority_breakdown": [
            {"priority": p, "count": c} for p, c in sorted(by_priority.items())
        ],
        "currency_breakdown": currency_breakdown,
    }
