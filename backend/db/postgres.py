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
            # ── Roles ─────────────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    role_id  INT PRIMARY KEY,
                    name     TEXT NOT NULL,
                    label    TEXT NOT NULL
                )
            """)
            cur.execute("""
                INSERT INTO roles (role_id, name, label) VALUES
                    (1, 'free',    'Free User'),
                    (2, 'premium', 'Premium User'),
                    (3, 'admin',   'Admin User')
                ON CONFLICT DO NOTHING
            """)

            # ── Users ─────────────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     UUID PRIMARY KEY,
                    name        TEXT,
                    email       TEXT,
                    role_id     INT NOT NULL DEFAULT 1 REFERENCES roles(role_id),
                    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            # Add new columns to pre-existing tables that only had user_id
            for col_sql in [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INT NOT NULL DEFAULT 1",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            ]:
                cur.execute(col_sql)

            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique
                ON users(email) WHERE email IS NOT NULL
            """)

            # ── Notebooks ─────────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notebooks (
                    notebook_id   UUID PRIMARY KEY,
                    user_id       UUID NOT NULL REFERENCES users(user_id),
                    title         TEXT NOT NULL DEFAULT 'Untitled notebook',
                    source_titles TEXT[] NOT NULL DEFAULT '{}',
                    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # ── OTPs ──────────────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS otps (
                    otp_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email      TEXT NOT NULL,
                    otp_code   TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    used       BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # ── Sessions ──────────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL
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
