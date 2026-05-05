from app.models.schemas import (
    ExplanationResponse,
    ExplainRequest,
    OptionAnalysis,
    Passage,
    TextbookBasis,
)
from app.services.knowledge_base import get_knowledge_base


def _option_display(label: str, text: str) -> str:
    return f"{label}. {text}".strip()


def _find_example_answer(question: str, passage: Passage) -> dict | None:
    kb = get_knowledge_base()
    section = kb.get_section_by_archive(passage.archive_chapter)
    if not section:
        return None

    question_chars = set(question)
    best_example = None
    best_score = 0
    for example in section.get("qa_examples", []):
        example_chars = set(example.get("question", ""))
        score = len(question_chars & example_chars)
        if score > best_score:
            best_score = score
            best_example = example
    return best_example


def _choose_option(request: ExplainRequest, passage: Passage, example: dict | None) -> tuple[str, str | None]:
    if example and example.get("answer"):
        answer = str(example["answer"])
        for option in request.options:
            if option.label.upper() in answer.upper() or option.text in answer:
                return _option_display(option.label, option.text), option.label
        return answer, None

    if not request.options:
        return "暂未识别到选项，建议结合教材依据人工确认。", None

    keyword_text = " ".join(passage.basis.keywords + passage.key_points + [passage.basis.quote])
    best_label = request.options[0].label
    best_text = request.options[0].text
    best_score = -1
    for option in request.options:
        score = 0
        for char in set(option.text):
            if char and char in keyword_text:
                score += 1
        if option.text in keyword_text:
            score += 5
        if score > best_score:
            best_score = score
            best_label = option.label
            best_text = option.text

    return _option_display(best_label, best_text), best_label


def build_explanation(request: ExplainRequest) -> ExplanationResponse:
    kb = get_knowledge_base()
    passages = kb.search(request.question, top_k=request.top_k)
    if not passages:
        raise ValueError("本地教材知识库未检索到相关章节，请补充教材 JSON 或调整题干。")

    primary = passages[0]
    example = _find_example_answer(request.question, primary)
    answer, selected_label = _choose_option(request, primary, example)
    mnemonic = (
        example.get("mnemonic")
        if example and example.get("mnemonic")
        else _fallback_mnemonic(primary.basis.keywords)
    )

    basis = [
        TextbookBasis(
            book_title=passage.basis.book_title,
            chapter_title=passage.basis.chapter_title,
            section_title=passage.basis.section_title,
            quote=passage.basis.quote,
            keywords=passage.basis.keywords,
        )
        for passage in passages
    ]

    why_correct = _why_correct(primary, example)
    why_others = _why_others(request, selected_label, primary)

    return ExplanationResponse(
        question=request.question,
        answer=answer,
        textbook_basis=basis,
        why_correct=why_correct,
        why_others=why_others,
        mnemonic=mnemonic,
        archive_chapter=primary.archive_chapter,
        related_key_points=primary.key_points,
    )


def _why_correct(primary: Passage, example: dict | None) -> str:
    if example and example.get("explanation"):
        return str(example["explanation"])
    keyword_hint = "、".join(primary.basis.keywords[:4]) or primary.basis.section_title
    return (
        f"题干核心信息与“{primary.basis.section_title}”相符，教材关键词集中在"
        f"“{keyword_hint}”。因此应优先围绕该章节的定义、主治或辨证要点作答。"
    )


def _why_others(request: ExplainRequest, selected_label: str | None, primary: Passage) -> list[OptionAnalysis]:
    if not request.options:
        return [
            OptionAnalysis(
                option="未识别选项",
                reason="OCR 未稳定拆出选项，建议先人工校正选项文本后再次生成解析。",
            )
        ]

    analyses: list[OptionAnalysis] = []
    for option in request.options:
        if selected_label and option.label.upper() == selected_label.upper():
            continue
        analyses.append(
            OptionAnalysis(
                option=_option_display(option.label, option.text),
                reason=(
                    f"该项与本题归档章节“{primary.basis.chapter_title} - {primary.basis.section_title}”"
                    "的核心关键词吻合度较低，不能直接支撑题干所问。"
                ),
            )
        )
    return analyses


def _fallback_mnemonic(keywords: list[str]) -> str:
    if not keywords:
        return "先抓题干关键词，再回到教材定义、功效、主治三件事。"
    compact = "、".join(keywords[:3])
    return f"记住“{compact}”：见关键词，回章节，按教材原意选。"

