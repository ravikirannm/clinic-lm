import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from config import POSTGRES_DSN

_pool: ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=POSTGRES_DSN)


def init_schema() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id UUID PRIMARY KEY
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notebooks (
                    notebook_id  UUID PRIMARY KEY,
                    user_id      UUID NOT NULL REFERENCES users(user_id),
                    title        TEXT NOT NULL DEFAULT 'Untitled notebook',
                    source_titles TEXT[] NOT NULL DEFAULT '{}',
                    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()


@contextmanager
def get_conn():
    assert _pool is not None, "DB pool not initialised"
    conn = _pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
