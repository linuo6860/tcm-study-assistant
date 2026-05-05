import re
import shutil
import os
from threading import Thread
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import init_db
from app.models.schemas import (
    ExplainRequest,
    ExplanationResponse,
    OCRRequest,
    OCRResponse,
    Option,
    RetrieveRequest,
    RetrieveResponse,
    SaveQuestionRequest,
    SaveQuestionResponse,
    SavedQuestion,
    UploadResponse,
)
from app.services.explainer import build_explanation
from app.services.knowledge_base import get_knowledge_base
from app.services.ocr import ocr_service
from app.services.storage import list_saved_questions, save_question


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    get_knowledge_base()
    if os.getenv("OCR_BACKGROUND_WARMUP", "true").lower() not in {"0", "false", "no"}:
        Thread(target=ocr_service.warmup, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/ocr/status")
def get_ocr_status():
    return ocr_service.status()


@app.post("/api/upload", response_model=UploadResponse)
def upload_image(file: UploadFile = File(...)) -> UploadResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件。")

    suffix = Path(file.filename or "").suffix or ".png"
    upload_id = f"{uuid.uuid4().hex}{suffix}"
    target = settings.upload_dir / upload_id

    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return UploadResponse(
        upload_id=upload_id,
        filename=file.filename or upload_id,
        content_type=file.content_type,
        size=target.stat().st_size,
    )


@app.post("/api/ocr", response_model=OCRResponse)
def recognize_ocr(payload: OCRRequest) -> OCRResponse:
    image_path = _safe_upload_path(payload.upload_id)
    return ocr_service.recognize(payload.upload_id, image_path)


@app.post("/api/retrieve", response_model=RetrieveResponse)
def retrieve_knowledge(payload: RetrieveRequest) -> RetrieveResponse:
    kb = get_knowledge_base()
    return RetrieveResponse(query=payload.query, passages=kb.search(payload.query, payload.top_k))


@app.post("/api/explain", response_model=ExplanationResponse)
def explain_question(payload: ExplainRequest) -> ExplanationResponse:
    try:
        return build_explanation(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/solve", response_model=ExplanationResponse)
def solve_from_image(file: UploadFile = File(...), corrected_text: str | None = Form(default=None)) -> ExplanationResponse:
    upload = upload_image(file)
    ocr = recognize_ocr(OCRRequest(upload_id=upload.upload_id))
    question_text = corrected_text or ocr.text
    question, options = split_question_and_options(question_text)
    return explain_question(ExplainRequest(question=question, options=options))


@app.post("/api/questions/save", response_model=SaveQuestionResponse)
def save_wrong_question(payload: SaveQuestionRequest) -> SaveQuestionResponse:
    saved_id = save_question(
        explanation=payload.explanation,
        raw_ocr=payload.raw_ocr,
        is_wrong=payload.is_wrong,
        note=payload.note,
    )
    return SaveQuestionResponse(id=saved_id, message="已保存到错题与知识点库。")


@app.get("/api/questions/saved", response_model=list[SavedQuestion])
def get_saved_questions() -> list[SavedQuestion]:
    return list_saved_questions()


@app.get("/api/knowledge/tree")
def get_knowledge_tree():
    return get_knowledge_base().chapter_tree()


def _safe_upload_path(upload_id: str) -> Path:
    candidate = (settings.upload_dir / upload_id).resolve()
    upload_root = settings.upload_dir.resolve()
    if upload_root not in candidate.parents and candidate != upload_root:
        raise HTTPException(status_code=400, detail="非法 upload_id。")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="未找到上传图片。")
    return candidate


def split_question_and_options(text: str) -> tuple[str, list[Option]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    option_pattern = re.compile(r"^([A-EＡ-Ｅ])[\.\。．、:：]?\s*(.+)$", re.IGNORECASE)
    question_lines: list[str] = []
    options: list[Option] = []

    for line in lines:
        match = option_pattern.match(line)
        if match:
            label = match.group(1).upper()
            label = chr(ord("A") + ord(label) - ord("Ａ")) if "Ａ" <= label <= "Ｅ" else label
            options.append(Option(label=label, text=match.group(2).strip()))
        else:
            question_lines.append(line)

    return "\n".join(question_lines) or text, options
