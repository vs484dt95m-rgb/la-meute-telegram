
import os
import psycopg

DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=15
    )


def init_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS publications (
                item_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT,
                published_at TEXT,
                detected_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

    print("PostgreSQL : base initialisée")


def already_published(item_id):
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT 1 FROM publications
            WHERE item_id = %s
            """,
            (item_id,)
        ).fetchone()

    return result is not None


def save_publication(item_id, source, title, published_at):
    with get_connection() as conn:
        result = conn.execute(
            """
            INSERT INTO publications
            (item_id, source, title, published_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (item_id) DO NOTHING
            RETURNING item_id
            """,
            (item_id, source, title, published_at)
        ).fetchone()

    return result is not None


def has_publications():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM publications)"
        ).fetchone()

    return result[0]
