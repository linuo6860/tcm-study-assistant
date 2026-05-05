import json
import os
from typing import Any

import requests

from app.models.schemas import (
    ArchiveChapter,
    ExplainRequest,
    ExplanationResponse,
    OptionAnalysis,
    Passage,
    TextbookBasis,
)


class LLMNotConfiguredError(RuntimeError):
    pass


class LLMGenerationError(RuntimeError):
    pass


def get_answer_mode() -> str:
    mode = os.getenv("ANSWER_MODE", "local").strip().lower()
    return mode if mode in {"local", "hybrid", "llm"} else "local"


def get_llm_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider in {"claude", "anthropic"}:
        return "anthropic"
    return "openai"


def answer_service_status() -> dict[str, Any]:
    provider = get_llm_provider()
    return {
        "mode": get_answer_mode(),
        "provider": provider,
        "ready": _provider_api_key(provider) is not None,
        "model": _provider_model(provider),
    }


def build_llm_explanation(
    request: ExplainRequest,
    passages: list[Passage],
    fallback: ExplanationResponse | None = None,
) -> ExplanationResponse:
    provider = get_llm_provider()
    if not _provider_api_key(provider):
        raise LLMNotConfiguredError(f"{provider} API key 未配置。")

    prompt = _build_prompt(request, passages)
    raw_text = _call_provider(provider, prompt)
    draft = _extract_json(raw_text)

    basis = fallback.textbook_basis if fallback else _basis_from_passages(passages)
    archive = fallback.archive_chapter if fallback else _archive_from_passages(passages)
    related_key_points = fallback.related_key_points if fallback else _key_points_from_passages(passages)

    why_others = _normalize_why_others(draft.get("why_others"), request)
    answer = _clean_text(draft.get("answer")) or (fallback.answer if fallback else "需人工确认")
    why_correct = _clean_text(draft.get("why_correct")) or (
        fallback.why_correct if fallback else "AI 未返回稳定解析，建议人工核对教材。"
    )
    mnemonic = _clean_text(draft.get("mnemonic")) or (
        fallback.mnemonic if fallback else "先核题干，再核教材依据，最后核选项边界。"
    )

    return ExplanationResponse(
        question=request.question,
        answer=answer,
        textbook_basis=basis,
        why_correct=why_correct,
        why_others=why_others,
        mnemonic=mnemonic,
        archive_chapter=archive,
        related_key_points=related_key_points,
        answer_source=f"llm:{provider}",
    )


def _provider_api_key(provider: str) -> str | None:
    key_name = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
    value = os.getenv(key_name, "").strip()
    return value or None


def _provider_model(provider: str) -> str:
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest").strip()
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()


def _call_provider(provider: str, prompt: str) -> str:
    if provider == "anthropic":
        return _call_anthropic(prompt)
    return _call_openai(prompt)


def _call_openai(prompt: str) -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = _provider_model("openai")
    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1600"))
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {_provider_api_key('openai')}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": "你是严谨的中医考试学习助手，只输出 JSON，不输出 Markdown。",
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=timeout,
    )
    return _response_text(response)


def _call_anthropic(prompt: str) -> str:
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    model = _provider_model("anthropic")
    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1600"))
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    response = requests.post(
        f"{base_url}/v1/messages",
        headers={
            "x-api-key": _provider_api_key("anthropic") or "",
            "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system": "你是严谨的中医考试学习助手，只输出 JSON，不输出 Markdown。",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    return _response_text(response)


def _response_text(response: requests.Response) -> str:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise LLMGenerationError(f"LLM API 调用失败：{response.text[:300]}") from exc

    data = response.json()
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    if "content" in data and data["content"]:
        return "".join(part.get("text", "") for part in data["content"] if part.get("type") == "text")
    raise LLMGenerationError("LLM API 未返回可解析文本。")


def _build_prompt(request: ExplainRequest, passages: list[Passage]) -> str:
    options = "\n".join(f"{option.label}. {option.text}" for option in request.options) or "未识别到选项"
    context = _format_passages(passages)
    return f"""
请根据中医考试题生成结构化讲解。

硬性规则：
1. 优先依据“教材检索片段”；片段不足时可以用通用中医知识推理，但必须在解析中说明“需核对教材”。
2. 不要编造不存在的教材书名、章节或原文。
3. 如果题目是“不属于、不是、不正确、错误、除外、不包括”等反向题，要选择最不符合题干要求的一项。
4. 如果无法稳定判断，answer 写“需人工确认：...”。
5. 只返回一个 JSON 对象，不要 Markdown、不要代码块。

JSON 字段：
{{
  "answer": "答案，尽量写成 A. 选项文本",
  "why_correct": "为什么选这个，结合教材或推理说明",
  "why_others": [
    {{"option": "A. 选项文本", "reason": "为什么不选"}}
  ],
  "mnemonic": "一句话记忆口诀"
}}

【题目】
{request.question}

【选项】
{options}

【教材检索片段】
{context}
""".strip()


def _format_passages(passages: list[Passage]) -> str:
    if not passages:
        return "本地教材知识库未命中。"

    chunks: list[str] = []
    for index, passage in enumerate(passages, start=1):
        basis = passage.basis
        key_points = "；".join(passage.key_points)
        keywords = "、".join(basis.keywords)
        chunks.append(
            f"[{index}] 《{basis.book_title}》{basis.chapter_title} - {basis.section_title}\n"
            f"关键词：{keywords}\n"
            f"教材片段：{basis.quote}\n"
            f"要点：{key_points}"
        )
    return "\n\n".join(chunks)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMGenerationError("LLM 返回内容不是 JSON。")

    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMGenerationError("LLM 返回 JSON 解析失败。") from exc


def _normalize_why_others(value: Any, request: ExplainRequest) -> list[OptionAnalysis]:
    analyses: list[OptionAnalysis] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            option = _clean_text(item.get("option"))
            reason = _clean_text(item.get("reason"))
            if option and reason:
                analyses.append(OptionAnalysis(option=option, reason=reason))

    if analyses:
        return analyses

    return [
        OptionAnalysis(
            option=f"{option.label}. {option.text}",
            reason="AI 未返回该选项的单独解析，建议结合题干和教材依据复核。",
        )
        for option in request.options
    ]


def _basis_from_passages(passages: list[Passage]) -> list[TextbookBasis]:
    if passages:
        return [passage.basis for passage in passages]
    return [
        TextbookBasis(
            book_title="AI 生成讲解",
            chapter_title="未归档",
            section_title="需人工确认",
            quote="本地教材知识库未命中，以下答案讲解来自模型推理，建议回到教材原文核对。",
            keywords=[],
        )
    ]


def _archive_from_passages(passages: list[Passage]) -> ArchiveChapter:
    if passages:
        return passages[0].archive_chapter
    return ArchiveChapter(
        book_id="llm-generated",
        book_title="AI 生成讲解",
        chapter_id="unclassified",
        chapter_title="未归档",
        section_id="manual-review",
        section_title="需人工确认",
        order_path=[999, 999, 999],
    )


def _key_points_from_passages(passages: list[Passage]) -> list[str]:
    points: list[str] = []
    for passage in passages:
        points.extend(passage.key_points)
    return points


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
