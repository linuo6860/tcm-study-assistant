import json
import sqlite3
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.models.schemas import ExplanationResponse, SavedQuestion


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def save_question(
    explanation: ExplanationResponse,
    raw_ocr: str | None,
    is_wrong: bool,
    note: str | None,
) -> int:
    payload = _model_dump(explanation)
    archive = explanation.archive_chapter
    archive_path = (
        f"{archive.book_title} / {archive.chapter_title} / {archive.section_title}"
    )

    with sqlite3.connect(settings.sqlite_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO saved_questions (
                question, answer, raw_ocr, explanation_json, archive_path,
                is_wrong, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                explanation.question,
                explanation.answer,
                raw_ocr,
                json.dumps(payload, ensure_ascii=False),
                archive_path,
                1 if is_wrong else 0,
                note,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return int(cursor.lastrowid)


def list_saved_questions() -> list[SavedQuestion]:
    with sqlite3.connect(settings.sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, question, answer, explanation_json, archive_path,
                   is_wrong, note, created_at
            FROM saved_questions
            ORDER BY created_at DESC
            """
        ).fetchall()

    items: list[SavedQuestion] = []
    for row in rows:
        items.append(
            SavedQuestion(
                id=int(row["id"]),
                question=row["question"],
                answer=row["answer"],
                archive_path=row["archive_path"],
                is_wrong=bool(row["is_wrong"]),
                note=row["note"],
                created_at=row["created_at"],
                explanation=json.loads(row["explanation_json"]),
            )
        )
    return items

