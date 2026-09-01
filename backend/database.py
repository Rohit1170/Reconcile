from pymongo import MongoClient
from pymongo.database import Database

from config import settings

_client: MongoClient = MongoClient(settings.mongodb_uri)
_db: Database = _client[settings.database_name]


def get_db() -> Database:
    """Single shared Database handle. PyMongo's client is thread-safe and
    pools connections internally, so one global client is the simplest
    correct option here -- no need for per-request connection management."""
    return _db
