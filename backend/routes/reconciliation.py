from decimal import Decimal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user
from database import get_db
from models import (
    DiscrepancyCategory,
    DiscrepancyDetailResponse,
    DiscrepancyListItem,
    DiscrepancyListResponse,
    DiscrepancyStatus,
    ReconciliationSummary,
)
from reconciliation import reconcile, summarize

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


def _require_dataset(db, user_id: str, reconciliation_id: str) -> dict:
    try:
        oid = ObjectId(reconciliation_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    dataset = db.datasets.find_one({"_id": oid, "user_id": user_id})
    if not dataset:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    return dataset


def _to_plain(doc: dict) -> dict:
    clean = {k: v for k, v in doc.items() if k not in ("_id", "user_id", "reconciliation_id")}
    clean["amount"] = Decimal(clean["amount"])
    return clean


@router.post("/run/{reconciliation_id}")
def run_reconciliation(reconciliation_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    user_id = str(user["_id"])
    _require_dataset(db, user_id, reconciliation_id)

    orders = [_to_plain(d) for d in db.orders.find({"reconciliation_id": reconciliation_id, "user_id": user_id})]
    payments = [_to_plain(d) for d in db.payments.find({"reconciliation_id": reconciliation_id, "user_id": user_id})]

    results = reconcile(orders, payments)

    db.reconciliations.delete_many({"reconciliation_id": reconciliation_id, "user_id": user_id})
    if results:
        db.reconciliations.insert_many([
            {**r, "user_id": user_id, "reconciliation_id": reconciliation_id} for r in results
        ])
    db.datasets.update_one({"_id": ObjectId(reconciliation_id)}, {"$set": {"status": "reconciled"}})

    return {"reconciliation_id": reconciliation_id, "discrepancies_created": len(results)}


@router.get("/{reconciliation_id}/summary", response_model=ReconciliationSummary)
def get_summary(reconciliation_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    user_id = str(user["_id"])
    _require_dataset(db, user_id, reconciliation_id)

    rows = list(db.reconciliations.find({"reconciliation_id": reconciliation_id, "user_id": user_id}))
    if not rows:
        raise HTTPException(status_code=404, detail="Reconciliation has not been run yet. Call /reconciliation/run/{id} first.")

    summary = summarize(rows)
    return ReconciliationSummary(reconciliation_id=reconciliation_id, **summary)


@router.get("/{reconciliation_id}/discrepancies", response_model=DiscrepancyListResponse)
def list_discrepancies(
    reconciliation_id: str,
    user: dict = Depends(get_current_user),
    search: str | None = None,
    category: DiscrepancyCategory | None = None,
    status: DiscrepancyStatus | None = None,
    currency: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    db = get_db()
    user_id = str(user["_id"])
    _require_dataset(db, user_id, reconciliation_id)

    query: dict = {"reconciliation_id": reconciliation_id, "user_id": user_id}
    if category:
        query["category"] = category.value
    if status:
        query["status"] = status.value
    if currency:
        query["$or"] = [{"order_currency": currency.upper()}, {"payment_currency": currency.upper()}]
    if search:
        # Backend-side filtering, as required: search order_id or payment_id.
        query["$and"] = query.get("$and", []) + [{
            "$or": [
                {"order_id": {"$regex": search, "$options": "i"}},
                {"payment_id": {"$regex": search, "$options": "i"}},
            ]
        }]

    total = db.reconciliations.count_documents(query)
    cursor = (
        db.reconciliations.find(query)
        .sort("_id", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    items = [
        DiscrepancyListItem(
            id=str(doc["_id"]),
            order_id=doc.get("order_id"),
            payment_id=doc.get("payment_id"),
            category=doc["category"],
            priority=doc["priority"],
            status=doc["status"],
            order_amount=doc.get("order_amount"),
            payment_amount=doc.get("payment_amount"),
            difference=doc.get("difference"),
            currency=doc.get("order_currency") or doc.get("payment_currency"),
            reason=doc["reason"],
        )
        for doc in cursor
    ]

    return DiscrepancyListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{reconciliation_id}/discrepancies/{discrepancy_id}", response_model=DiscrepancyDetailResponse)
def get_discrepancy(reconciliation_id: str, discrepancy_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    user_id = str(user["_id"])
    _require_dataset(db, user_id, reconciliation_id)

    try:
        oid = ObjectId(discrepancy_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Discrepancy not found")

    doc = db.reconciliations.find_one({"_id": oid, "reconciliation_id": reconciliation_id, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Discrepancy not found")

    return DiscrepancyDetailResponse(
        id=str(doc["_id"]),
        order=doc.get("order"),
        payment=doc.get("payment"),
        category=doc["category"],
        priority=doc["priority"],
        status=doc["status"],
        difference=doc.get("difference"),
        order_currency=doc.get("order_currency"),
        payment_currency=doc.get("payment_currency"),
        reason=doc["reason"],
        financial_impact=doc.get("financial_impact", 0.0),
    )
