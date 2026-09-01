from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth import get_current_user
from csv_parser import CSVParseError, parse_orders_csv, parse_payments_csv
from database import get_db
from models import DatasetUploadResponse

router = APIRouter(prefix="/datasets", tags=["datasets"])

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
SAMPLE_ORDERS = SAMPLE_DIR / "orders.csv"
SAMPLE_PAYMENTS = SAMPLE_DIR / "payments.csv"


def _serialize(record: dict) -> dict:
    """Decimal -> str for safe, exact-round-trip Mongo storage."""
    return {**record, "amount": str(record["amount"])}


def _store_dataset(user_id: str, orders: list[dict], payments: list[dict]) -> str:
    db = get_db()
    dataset = db.datasets.insert_one({
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
        "orders_imported": len(orders),
        "payments_imported": len(payments),
        "status": "uploaded",
    })
    reconciliation_id = str(dataset.inserted_id)

    if orders:
        db.orders.insert_many([
            {**_serialize(o), "user_id": user_id, "reconciliation_id": reconciliation_id} for o in orders
        ])
    if payments:
        db.payments.insert_many([
            {**_serialize(p), "user_id": user_id, "reconciliation_id": reconciliation_id} for p in payments
        ])

    return reconciliation_id


@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_datasets(
    orders_file: UploadFile = File(...),
    payments_file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    for f in (orders_file, payments_file):
        if not f.filename or not f.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail=f"'{f.filename}' must be a .csv file")

    try:
        orders = parse_orders_csv(await orders_file.read())
        payments = parse_payments_csv(await payments_file.read())
    except CSVParseError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not orders and not payments:
        raise HTTPException(status_code=400, detail="No valid rows found in either file")

    reconciliation_id = _store_dataset(str(user["_id"]), orders, payments)
    return DatasetUploadResponse(
        reconciliation_id=reconciliation_id,
        orders_imported=len(orders),
        payments_imported=len(payments),
    )


@router.post("/demo", response_model=DatasetUploadResponse)
async def load_demo_data(user: dict = Depends(get_current_user)):
    if not SAMPLE_ORDERS.exists() or not SAMPLE_PAYMENTS.exists():
        raise HTTPException(
            status_code=404,
            detail="Sample data not found. Place orders.csv and payments.csv in backend/sample_data/.",
        )

    try:
        orders = parse_orders_csv(SAMPLE_ORDERS.read_bytes())
        payments = parse_payments_csv(SAMPLE_PAYMENTS.read_bytes())
    except CSVParseError as e:
        raise HTTPException(status_code=500, detail=f"Sample data is invalid: {e}")

    reconciliation_id = _store_dataset(str(user["_id"]), orders, payments)
    return DatasetUploadResponse(
        reconciliation_id=reconciliation_id,
        orders_imported=len(orders),
        payments_imported=len(payments),
    )
