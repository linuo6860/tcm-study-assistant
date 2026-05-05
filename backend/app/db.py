import sqlite3

from app.core.config import settings


def init_db() -> None:
    settings.ensure_directories()
    with sqlite3.connect(settings.sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                raw_ocr TEXT,
                explanation_json TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                is_wrong INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_saved_questions_archive
            ON saved_questions(archive_path)
            """
        )

