from typing import Any

from pydantic import BaseModel, Field


class Option(BaseModel):
    label: str = Field(..., examples=["A"])
    text: str = Field(..., examples=["阴阳互根"])


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    content_type: str | None = None
    size: int


class OCRRequest(BaseModel):
    upload_id: str


class OCRBlock(BaseModel):
    text: str
    confidence: float | None = None
    box: list[Any] | None = None


class OCRResponse(BaseModel):
    upload_id: str
    text: str
    blocks: list[OCRBlock] = Field(default_factory=list)
    engine: str
    warning: str | None = None


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=10)


class ArchiveChapter(BaseModel):
    book_id: str
    book_title: str
    chapter_id: str
    chapter_title: str
    section_id: str
    section_title: str
    order_path: list[int]


class TextbookBasis(BaseModel):
    book_title: str
    chapter_title: str
    section_title: str
    quote: str
    keywords: list[str] = Field(default_factory=list)


class Passage(BaseModel):
    id: str
    score: float
    archive_chapter: ArchiveChapter
    basis: TextbookBasis
    key_points: list[str] = Field(default_factory=list)


class RetrieveResponse(BaseModel):
    query: str
    passages: list[Passage]


class ExplainRequest(BaseModel):
    question: str
    options: list[Option] = Field(default_factory=list)
    top_k: int = Field(default=3, ge=1, le=10)


class OptionAnalysis(BaseModel):
    option: str
    reason: str


class ExplanationResponse(BaseModel):
    question: str
    answer: str
    textbook_basis: list[TextbookBasis]
    why_correct: str
    why_others: list[OptionAnalysis]
    mnemonic: str
    archive_chapter: ArchiveChapter
    related_key_points: list[str] = []


class SaveQuestionRequest(BaseModel):
    raw_ocr: str | None = None
    explanation: ExplanationResponse
    is_wrong: bool = True
    note: str | None = None


class SavedQuestion(BaseModel):
    id: int
    question: str
    answer: str
    archive_path: str
    is_wrong: bool
    note: str | None = None
    created_at: str
    explanation: dict[str, Any]


class SaveQuestionResponse(BaseModel):
    id: int
    message: str


class KnowledgeTreeNode(BaseModel):
    id: str
    title: str
    type: str
    order: int = 0
    children: list["KnowledgeTreeNode"] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)


KnowledgeTreeNode.model_rebuild()
