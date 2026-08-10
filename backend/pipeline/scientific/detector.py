from __future__ import annotations

import re
from pathlib import Path

from backend.pipeline.scientific.models import DocumentProfile, RequestedDocumentProfile


_ABSTRACT_RE = re.compile(r"(?im)^\s*(abstract|resumo)\s*$")
_KEYWORDS_RE = re.compile(r"(?im)^\s*(keywords?|palavras[- ]chave)\s*[:\-]?")
_REFERENCES_RE = re.compile(
    r"(?im)^\s*(references|bibliography|refer[eê]ncias bibliogr[aá]ficas|refer[eê]ncias)\s*$"
)
_SECTION_PATTERNS = {
    "introduction": re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*\s+)?(introduction|introdu[cç][aã]o)\s*$"),
    "methods": re.compile(
        r"(?im)^\s*(?:\d+(?:\.\d+)*\s+)?(methods?|methodology|materials and methods|m[eé]todos|metodologia)\s*$"
    ),
    "results": re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*\s+)?(results?|resultados)\s*$"),
    "discussion": re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*\s+)?(discussion|discuss[aã]o)\s*$"),
    "conclusion": re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*\s+)?(conclusions?|conclus[oõ]es?)\s*$"),
}
_FIGURE_RE = re.compile(r"(?im)^\s*(fig(?:ure|ura)?\.?\s*\d+[a-z]?)\b")
_TABLE_RE = re.compile(r"(?im)^\s*(table|tabela)\s+\d+[a-z]?\b")
_NUMBERED_REFERENCE_RE = re.compile(r"(?m)^\s*\[\d{1,3}\]\s+\S+")
_AUTHOR_YEAR_CITATION_RE = re.compile(
    r"\([A-ZÀ-Ý][\wÀ-ÿ'’-]+(?:\s+et\s+al\.)?,?\s+(?:19|20)\d{2}[a-z]?\)"
)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_ARXIV_RE = re.compile(r"\barXiv:\d{4}\.\d{4,5}(?:v\d+)?\b", re.IGNORECASE)


def detect_document_profile(
    file_path: Path,
    requested_profile: RequestedDocumentProfile = "auto",
    *,
    max_pages: int = 8,
) -> DocumentProfile:
    if requested_profile not in {"auto", "scientific", "general"}:
        raise ValueError("document_profile invalido; use auto, scientific ou general")

    if requested_profile != "auto":
        return DocumentProfile(
            requested_profile=requested_profile,
            effective_profile=requested_profile,
            decision_source="override",
            confidence=1.0,
            evidence=[f"override:{requested_profile}"],
        )

    if file_path.suffix.lower() != ".pdf":
        return DocumentProfile(
            requested_profile="auto",
            effective_profile="general",
            decision_source="unsupported",
            confidence=1.0,
            evidence=["non-pdf-input"],
        )

    text, metadata = _read_pdf_signals(file_path, max_pages=max_pages)
    return detect_profile_from_text(text, metadata=metadata)


def detect_profile_from_text(
    text: str,
    *,
    metadata: dict[str, str] | None = None,
) -> DocumentProfile:
    evidence: list[str] = []
    score = 0

    if _ABSTRACT_RE.search(text):
        score += 3
        evidence.append("abstract-heading")
    if _KEYWORDS_RE.search(text):
        score += 1
        evidence.append("keywords")
    if _REFERENCES_RE.search(text):
        score += 3
        evidence.append("reference-section")

    detected_sections = [
        name for name, pattern in _SECTION_PATTERNS.items() if pattern.search(text)
    ]
    if len(detected_sections) >= 2:
        score += 2
        evidence.append("academic-sections:" + ",".join(detected_sections))
    if len(detected_sections) >= 4:
        score += 1

    figure_count = len(_FIGURE_RE.findall(text))
    table_count = len(_TABLE_RE.findall(text))
    if figure_count + table_count >= 2:
        score += 1
        evidence.append("numbered-figures-or-tables")

    citation_count = len(_NUMBERED_REFERENCE_RE.findall(text)) + len(
        _AUTHOR_YEAR_CITATION_RE.findall(text)
    )
    if citation_count >= 3:
        score += 2
        evidence.append("citation-density")

    if _DOI_RE.search(text):
        score += 1
        evidence.append("doi")
    if _ARXIV_RE.search(text):
        score += 2
        evidence.append("arxiv-identifier")

    normalized_metadata = {
        str(key).lower(): str(value).strip()
        for key, value in (metadata or {}).items()
        if value
    }
    if normalized_metadata.get("author") and normalized_metadata.get("title"):
        score += 1
        evidence.append("title-and-author-metadata")

    is_scientific = score >= 6 and len(evidence) >= 2
    confidence = min(0.99, 0.5 + abs(score - 5) * 0.08)
    return DocumentProfile(
        requested_profile="auto",
        effective_profile="scientific" if is_scientific else "general",
        decision_source="detector",
        confidence=round(confidence, 2),
        evidence=evidence,
    )


def _read_pdf_signals(file_path: Path, *, max_pages: int) -> tuple[str, dict[str, str]]:
    import fitz

    with fitz.open(file_path) as document:
        page_text = [
            document[page_index].get_text("text")
            for page_index in range(min(len(document), max_pages))
        ]
        metadata = {
            str(key): str(value)
            for key, value in (document.metadata or {}).items()
            if value
        }
    return "\n".join(page_text), metadata