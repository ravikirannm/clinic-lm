from pymongo import MongoClient
from pymongo.database import Database
from config import MONGODB_URI

_client: MongoClient | None = None


def get_db() -> Database:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client.get_default_database()
