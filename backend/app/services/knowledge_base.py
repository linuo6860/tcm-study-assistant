import json
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.models.schemas import ArchiveChapter, KnowledgeTreeNode, Passage, TextbookBasis


def _normalize(text: str) -> str:
    return "".join(text.lower().split())


def _char_overlap_score(query: str, text: str) -> float:
    query_chars = set(_normalize(query))
    if not query_chars:
        return 0.0
    text_chars = set(_normalize(text))
    return len(query_chars & text_chars) / len(query_chars)


class KnowledgeBase:
    def __init__(self, json_path: Path | None = None) -> None:
        self.json_path = json_path or settings.textbook_json_path
        self.data = self._load_json()

    def _load_json(self) -> dict:
        with self.json_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def search(self, query: str, top_k: int = 3) -> list[Passage]:
        candidates: list[Passage] = []

        for book in self.data.get("books", []):
            for chapter in book.get("chapters", []):
                for section in chapter.get("sections", []):
                    score = self._score_section(query, book, chapter, section)
                    if score <= 0:
                        continue

                    archive = ArchiveChapter(
                        book_id=book["id"],
                        book_title=book["title"],
                        chapter_id=chapter["id"],
                        chapter_title=chapter["title"],
                        section_id=section["id"],
                        section_title=section["title"],
                        order_path=[
                            int(book.get("order", 0)),
                            int(chapter.get("order", 0)),
                            int(section.get("order", 0)),
                        ],
                    )
                    basis = TextbookBasis(
                        book_title=book["title"],
                        chapter_title=chapter["title"],
                        section_title=section["title"],
                        quote=section.get("content", ""),
                        keywords=section.get("keywords", []),
                    )
                    candidates.append(
                        Passage(
                            id=f"{book['id']}::{chapter['id']}::{section['id']}",
                            score=round(score, 4),
                            archive_chapter=archive,
                            basis=basis,
                            key_points=section.get("key_points", []),
                        )
                    )

        return sorted(candidates, key=lambda item: item.score, reverse=True)[:top_k]

    def _score_section(self, query: str, book: dict, chapter: dict, section: dict) -> float:
        searchable = " ".join(
            [
                book.get("title", ""),
                chapter.get("title", ""),
                section.get("title", ""),
                section.get("content", ""),
                " ".join(section.get("keywords", [])),
                " ".join(section.get("key_points", [])),
                " ".join(example.get("question", "") for example in section.get("qa_examples", [])),
                " ".join(example.get("answer", "") for example in section.get("qa_examples", [])),
            ]
        )
        score = _char_overlap_score(query, searchable) * 3

        normalized_query = _normalize(query)
        for keyword in section.get("keywords", []):
            if _normalize(keyword) and _normalize(keyword) in normalized_query:
                score += 6

        if _normalize(section.get("title", "")) in normalized_query:
            score += 4
        if _normalize(chapter.get("title", "")) in normalized_query:
            score += 2

        for example in section.get("qa_examples", []):
            score += _char_overlap_score(query, example.get("question", "")) * 2

        return score

    def get_section_by_archive(self, archive: ArchiveChapter) -> dict | None:
        for book in self.data.get("books", []):
            if book.get("id") != archive.book_id:
                continue
            for chapter in book.get("chapters", []):
                if chapter.get("id") != archive.chapter_id:
                    continue
                for section in chapter.get("sections", []):
                    if section.get("id") == archive.section_id:
                        return section
        return None

    def chapter_tree(self) -> list[KnowledgeTreeNode]:
        tree: list[KnowledgeTreeNode] = []
        for book in sorted(self.data.get("books", []), key=lambda item: item.get("order", 0)):
            book_node = KnowledgeTreeNode(
                id=book["id"],
                title=book["title"],
                type="book",
                order=int(book.get("order", 0)),
                children=[],
            )
            for chapter in sorted(book.get("chapters", []), key=lambda item: item.get("order", 0)):
                chapter_node = KnowledgeTreeNode(
                    id=chapter["id"],
                    title=chapter["title"],
                    type="chapter",
                    order=int(chapter.get("order", 0)),
                    children=[],
                )
                for section in sorted(chapter.get("sections", []), key=lambda item: item.get("order", 0)):
                    section_node = KnowledgeTreeNode(
                        id=section["id"],
                        title=section["title"],
                        type="section",
                        order=int(section.get("order", 0)),
                        keywords=section.get("keywords", []),
                        key_points=section.get("key_points", []),
                    )
                    chapter_node.children.append(section_node)
                book_node.children.append(chapter_node)
            tree.append(book_node)
        return tree


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase()

