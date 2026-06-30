import logging

from pymongo import MongoClient, ASCENDING
from pymongo.database import Database
from config import MONGODB_URI

logger = logging.getLogger(__name__)

_client: MongoClient | None = None


def get_db() -> Database:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client.get_default_database()


def init_indexes() -> None:
    """Create MongoDB indexes for fast notebook lookups. Safe to call repeatedly."""
    db = get_db()
    db.notebook_content.create_index(
        [("notebook_id", ASCENDING), ("user_id", ASCENDING)],
        unique=True,
        name="notebook_user_unique",
    )
    logger.info("MongoDB indexes ensured")
