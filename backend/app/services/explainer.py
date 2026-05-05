from difflib import SequenceMatcher

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


def _normalize_text(text: str) -> str:
    return "".join(str(text).lower().split())


def _similarity(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 1.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _find_example_answer(question: str, passage: Passage) -> dict | None:
    kb = get_knowledge_base()
    section = kb.get_section_by_archive(passage.archive_chapter)
    if not section:
        return None

    best_example = None
    best_score = 0.0
    for example in section.get("qa_examples", []):
        score = _similarity(question, example.get("question", ""))
        if score > best_score:
            best_score = score
            best_example = example
    return best_example if best_score >= 0.62 else None


def _choose_option(request: ExplainRequest, passage: Passage, example: dict | None) -> tuple[str, str | None, float]:
    if example and example.get("answer"):
        answer = str(example["answer"])
        for option in request.options:
            if _answer_matches_option(answer, option.label, option.text):
                return _option_display(option.label, option.text), option.label, 1.0
        return answer, None, 0.9

    if not request.options:
        return "暂未识别到选项，建议结合教材依据人工确认。", None, 0.0

    option_scores = _score_options(request, passage)
    if not option_scores:
        return "需人工确认：本地教材知识库不足以稳定判断该题答案。", None, 0.0

    negative_question = _is_negative_question(request.question)
    sorted_scores = sorted(option_scores, key=lambda item: item[2], reverse=not negative_question)
    selected = sorted_scores[0]
    runner_up = sorted_scores[1] if len(sorted_scores) > 1 else None
    margin = abs(selected[2] - runner_up[2]) if runner_up else selected[2]
    confidence = _score_to_confidence(selected[2], margin, negative_question)

    if confidence < 0.45:
        return (
            "需人工确认：教材检索结果与各选项区分度不足，系统不建议强行作答。",
            None,
            confidence,
        )

    return _option_display(selected[0], selected[1]), selected[0], confidence


def _answer_matches_option(answer: str, label: str, option_text: str) -> bool:
    normalized_answer = _normalize_text(answer)
    normalized_label = _normalize_text(label)
    normalized_option = _normalize_text(option_text)
    return (
        normalized_answer.startswith(normalized_label)
        or normalized_option in normalized_answer
        or normalized_answer in normalized_option
    )


def _score_options(request: ExplainRequest, passage: Passage) -> list[tuple[str, str, float]]:
    section_text = " ".join(
        passage.basis.keywords
        + passage.key_points
        + [passage.basis.quote, passage.basis.section_title, passage.basis.chapter_title]
    )
    section_norm = _normalize_text(section_text)
    scores: list[tuple[str, str, float]] = []

    for option in request.options:
        option_norm = _normalize_text(option.text)
        if not option_norm:
            scores.append((option.label, option.text, 0.0))
            continue

        score = 0.0
        if option_norm in section_norm:
            score += 8.0

        for keyword in passage.basis.keywords:
            keyword_norm = _normalize_text(keyword)
            if not keyword_norm:
                continue
            if option_norm == keyword_norm:
                score += 8.0
            elif option_norm in keyword_norm or keyword_norm in option_norm:
                score += 4.0
            else:
                score += _similarity(option.text, keyword) * 1.5

        for point in passage.key_points:
            point_norm = _normalize_text(point)
            if option_norm in point_norm:
                score += 3.0

        # Character overlap is only a weak tie-breaker, not enough to decide alone.
        option_chars = set(option_norm)
        section_chars = set(section_norm)
        if option_chars:
            score += len(option_chars & section_chars) / len(option_chars)

        scores.append((option.label, option.text, round(score, 4)))

    return scores


def _is_negative_question(question: str) -> bool:
    negative_markers = [
        "不属于",
        "不是",
        "不正确",
        "错误",
        "除外",
        "不包括",
        "无关",
        "不宜",
        "不应",
        "不符合",
        "不对",
        "为非",
        "何项为非",
        "哪项为非",
    ]
    normalized_question = _normalize_text(question)
    return any(marker in normalized_question for marker in negative_markers)


def _score_to_confidence(score: float, margin: float, negative_question: bool) -> float:
    if negative_question:
        if margin >= 3:
            return 0.72
        if margin >= 1.5:
            return 0.55
        return 0.3

    if score >= 8 and margin >= 2:
        return 0.82
    if score >= 4 and margin >= 1.5:
        return 0.62
    if score >= 2.5 and margin >= 1:
        return 0.48
    return 0.25


def build_explanation(request: ExplainRequest) -> ExplanationResponse:
    kb = get_knowledge_base()
    passages = kb.search(request.question, top_k=request.top_k)
    if not passages:
        raise ValueError("本地教材知识库未检索到相关章节，请补充教材 JSON 或调整题干。")

    primary = passages[0]
    example = _find_example_answer(request.question, primary)
    answer, selected_label, confidence = _choose_option(request, primary, example)
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

    why_correct = _why_correct(primary, example, confidence, selected_label)
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


def _why_correct(primary: Passage, example: dict | None, confidence: float, selected_label: str | None) -> str:
    if example and example.get("explanation"):
        return str(example["explanation"])
    if not selected_label:
        return (
            "当前教材 JSON 只检索到相关章节，但没有足够明确的例题答案或选项依据。"
            "为避免误导，建议先人工核对教材原文，或把该题补入教材知识库/题库示例后再自动判题。"
        )
    keyword_hint = "、".join(primary.basis.keywords[:4]) or primary.basis.section_title
    return (
        f"题干核心信息与“{primary.basis.section_title}”相符，教材关键词集中在"
        f"“{keyword_hint}”。当前选项匹配置信度约为 {confidence:.0%}，仍建议以教材原文复核。"
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
