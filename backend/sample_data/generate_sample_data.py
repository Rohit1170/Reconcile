"""Generates the synthetic demo dataset in this folder.

Not real business data -- see README.md. Deterministic (no randomness) so
regenerating produces byte-identical output. Deliberately includes messy
formatting (extra whitespace, lowercase currency, "$"/comma amounts,
mixed date formats) to exercise csv_parser.py's normalization, and at
least one order/payment pair for every DiscrepancyCategory to exercise
reconciliation.py end to end.

Run: python generate_sample_data.py
"""

import csv
from pathlib import Path

ORDERS = [
    # order_id,      customer_name,        order_date,   amount,    currency, status
    ("ORD-1001", "Ada Lovelace", "2026-08-01", "120.00", "USD", "paid"),
    ("ORD-1002", "Grace Hopper", "2026-08-01", "45.50", "usd", "paid"),
    ("ORD-1003", " Alan Turing ", "2026-08-02", "$300.00", "USD", "paid"),
    ("ORD-1004", "Margaret Hamilton", "08/02/2026", "89.99", "USD", "paid"),
    ("ORD-1005", "Katherine Johnson", "2026-08-03", "1,250.00", "USD", "paid"),
    ("ORD-1006", "Radia Perlman", "2026-08-03", "60.00", "USD", "paid"),
    ("ORD-1007", "Barbara Liskov", "2026-08-04", "15.25", "USD", "paid"),
    ("ORD-1008", "Frances Allen", "2026-08-04", "500.00", "USD", "paid"),
    ("ORD-1009", "Shafi Goldwasser", "2026-08-05", "72.10", "USD", "paid"),
    ("ORD-1010", "Adele Goldberg", "2026-08-05", "18.00", "USD", "paid"),
    # AMOUNT_MISMATCH
    ("ORD-1011", "Steve Wozniak", "2026-08-06", "200.00", "USD", "paid"),
    ("ORD-1012", "Linus Torvalds", "2026-08-06", "35.00", "USD", "paid"),
    # MISSING_PAYMENT (no row in payments.csv)
    ("ORD-1013", "Guido van Rossum", "2026-08-07", "99.00", "USD", "paid"),
    ("ORD-1014", "James Gosling", "2026-08-07", "150.00", "USD", "paid"),
    # DUPLICATE_ORDER: ORD-1015 appears twice below
    ("ORD-1015", "Dennis Ritchie", "2026-08-08", "40.00", "USD", "paid"),
    ("ORD-1015", "Dennis Ritchie", "2026-08-08", "40.00", "USD", "paid"),
    # CURRENCY_MISMATCH
    ("ORD-1016", "Bjarne Stroustrup", "2026-08-08", "80.00", "USD", "paid"),
    ("ORD-1017", "Anders Hejlsberg", "2026-08-09", "65.00", "EUR", "paid"),
    # REFUND_CHARGE_ISSUE: order still shows paid, payment was refunded
    ("ORD-1018", "Yukihiro Matsumoto", "2026-08-09", "220.00", "USD", "paid"),
    # ROUNDING_DIFFERENCE
    ("ORD-1019", "Rasmus Lerdorf", "2026-08-10", "49.99", "USD", "paid"),
    # DUPLICATE_PAYMENT target order
    ("ORD-1020", "Brendan Eich", "2026-08-10", "30.00", "USD", "paid"),
    # a couple more clean matches
    ("ORD-1021", "John Backus", "2026-08-11", "18.75", "USD", "paid"),
    ("ORD-1022", "Niklaus Wirth", "2026-08-11", "260.00", "USD", "paid"),
]

PAYMENTS = [
    # payment_id,   order_id,   payment_date, amount,   currency, status
    ("PAY-2001", "ORD-1001", "2026-08-01", "120.00", "USD", "succeeded"),
    ("PAY-2002", "ORD-1002", "2026-08-01", "45.50", "USD", "succeeded"),
    ("PAY-2003", "ORD-1003", "2026-08-02", "300.00", "usd", "succeeded"),
    ("PAY-2004", "ORD-1004", "2026-08-02", "89.99", "USD", "succeeded"),
    ("PAY-2005", "ORD-1005", "2026-08-03", "1250.00", "USD", "succeeded"),
    ("PAY-2006", "ORD-1006", "2026-08-03", "60.00", "USD", "succeeded"),
    ("PAY-2007", "ORD-1007", "2026-08-04", "15.25", "USD", "succeeded"),
    ("PAY-2008", "ORD-1008", "2026-08-04", "500.00", "USD", "succeeded"),
    ("PAY-2009", "ORD-1009", "2026-08-05", "72.10", "USD", "succeeded"),
    ("PAY-2010", "ORD-1010", "2026-08-05", "18.00", "USD", "succeeded"),
    # AMOUNT_MISMATCH: processor charged a different amount than the order total
    ("PAY-2011", "ORD-1011", "2026-08-06", "180.00", "USD", "succeeded"),
    ("PAY-2012", "ORD-1012", "2026-08-06", "42.00", "USD", "succeeded"),
    # ORD-1013 / ORD-1014: intentionally no payment row (MISSING_PAYMENT)
    # ORD-1015: no payment row either -- the duplicate order is the issue on its own
    ("PAY-2016", "ORD-1016", "2026-08-08", "80.00", "USD", "succeeded"),
    ("PAY-2017", "ORD-1017", "2026-08-09", "65.00", "USD", "succeeded"),  # CURRENCY_MISMATCH vs order's EUR
    ("PAY-2018", "ORD-1018", "2026-08-09", "220.00", "USD", "refunded"),  # REFUND_CHARGE_ISSUE
    ("PAY-2019", "ORD-1019", "2026-08-10", "50.00", "USD", "succeeded"),  # ROUNDING_DIFFERENCE (0.01 off)
    ("PAY-2020a", "ORD-1020", "2026-08-10", "30.00", "USD", "succeeded"),  # DUPLICATE_PAYMENT
    ("PAY-2020b", "ORD-1020", "2026-08-10", "30.00", "USD", "succeeded"),
    ("PAY-2021", "ORD-1021", "2026-08-11", "18.75", "USD", "succeeded"),
    ("PAY-2022", "ORD-1022", "2026-08-11", "260.00", "USD", "succeeded"),
    # UNKNOWN_PAYMENT: no order with this order_id exists
    ("PAY-2099", "ORD-9999", "2026-08-12", "44.00", "USD", "succeeded"),
]


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "orders.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["order_id", "customer_name", "order_date", "amount", "currency", "status"])
        writer.writerows(ORDERS)

    with open(out_dir / "payments.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["payment_id", "order_id", "payment_date", "amount", "currency", "status"])
        writer.writerows(PAYMENTS)

    print(f"Wrote {len(ORDERS)} orders and {len(PAYMENTS)} payments to {out_dir}")


if __name__ == "__main__":
    main()
