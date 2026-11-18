import os
from contextlib import contextmanager

import bcrypt
import psycopg2
import psycopg2.errors
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


class DatabaseError(Exception):
    """Database problem with a message that is safe to show in the UI."""


@contextmanager
def _cursor(dict_rows: bool = False):
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseError("DATABASE_URL is not set in your .env file.")
    try:
        conn = psycopg2.connect(url)
    except psycopg2.Error:
        # Don't include the raw error: it can contain connection details.
        raise DatabaseError("Could not connect to PostgreSQL. Check DATABASE_URL.") from None
    try:
        with conn:  # commits on success, rolls back on error
            with conn.cursor(cursor_factory=RealDictCursor if dict_rows else None) as cur:
                yield cur
    finally:
        conn.close()


def init_db():
    with _cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS research_reports (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                topic TEXT NOT NULL,
                report TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)


def create_user(username: str, password: str) -> int:
    """Create a user. Raises DatabaseError if the username is taken."""
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id;",
                (username, password_hash),
            )
            return cur.fetchone()[0]
    except psycopg2.errors.UniqueViolation:
        raise DatabaseError("That username is already taken.") from None


def verify_user(username: str, password: str):
    """Return the user's id if the credentials match, otherwise None."""
    with _cursor(dict_rows=True) as cur:
        cur.execute("SELECT id, password_hash FROM users WHERE username = %s;", (username,))
        row = cur.fetchone()
    if row is None:
        # Run a dummy check so response time doesn't reveal whether the username exists.
        bcrypt.checkpw(b"dummy", bcrypt.gensalt())
        return None
    if bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return row["id"]
    return None


def save_report(user_id: int, topic: str, report: str) -> int:
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO research_reports (user_id, topic, report) "
            "VALUES (%s, %s, %s) RETURNING id;",
            (user_id, topic, report),
        )
        return cur.fetchone()[0]


def get_user_reports(user_id: int, limit: int = 20):
    with _cursor(dict_rows=True) as cur:
        cur.execute(
            "SELECT id, topic, report, created_at FROM research_reports "
            "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s;",
            (user_id, limit),
        )
        return cur.fetchall()