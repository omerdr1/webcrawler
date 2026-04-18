import sqlite3
import threading
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_NAME = "crawler.db"

# Thread-local storage for connections — each thread gets its own connection
_local = threading.local()


def get_db_connection():
    """
    Returns a thread-local SQLite connection with WAL mode enabled.
    WAL (Write-Ahead Logging) allows concurrent readers while a writer is active,
    which is critical for searching while the indexer is running.
    """
    if not hasattr(_local, 'connection') or _local.connection is None:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.connection = conn
    return _local.connection


def close_thread_connection():
    """Closes the connection for the current thread."""
    if hasattr(_local, 'connection') and _local.connection is not None:
        _local.connection.close()
        _local.connection = None


def init_db():
    """Creates database tables if they don't exist."""
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS crawl_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin_url TEXT NOT NULL,
            max_depth INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            pages_crawled INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            url TEXT PRIMARY KEY,
            job_id INTEGER,
            origin_url TEXT NOT NULL,
            depth INTEGER NOT NULL,
            title TEXT,
            content_text TEXT,
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES crawl_jobs (id)
        )
        """)

        # Index for faster search queries
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pages_job_id ON pages(job_id)
        """)

        # Pending URLs table for resume support:
        # When a crawl is interrupted, unprocessed URLs are persisted here
        # so the job can be resumed without re-discovering the frontier.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            depth INTEGER NOT NULL,
            FOREIGN KEY (job_id) REFERENCES crawl_jobs (id)
        )
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pending_job ON pending_urls(job_id)
        """)

        conn.commit()
        logging.info("Database initialized successfully (WAL mode enabled).")
    except sqlite3.Error as e:
        logging.error(f"Database initialization error: {e}")
    finally:
        conn.close()