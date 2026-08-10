from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any


QUALITY_DIMENSIONS = (
    "title",
    "headings",
    "content",
    "figures",
    "tables",
    "formulas",
    "references",
    "contract",
)


def evaluate_scientific_quality(
    document: dict[str, Any],
    annotations: dict[str, Any],
) -> dict[str, Any]:
    blocks = list(_walk_blocks(document.get("sections", [])))
    all_text = _normalized_text(document)
    dimensions: dict[str, dict[str, Any]] = {}

    dimensions["title"] = _coverage(
        [str(annotations["title"]) if annotations.get("title") else ""],
        _normalized_text(document.get("title", "")),
    )

    expected_headings = _strings(annotations.get("headings"))
    actual_headings = _heading_texts(document, blocks)
    heading_coverage = _coverage(expected_headings, "\n".join(actual_headings))
    heading_coverage["order_accuracy"] = _order_accuracy(
        expected_headings,
        actual_headings,
    )
    if expected_headings:
        heading_coverage["score"] = round(
            (heading_coverage["score"] + heading_coverage["order_accuracy"]) / 2,
            4,
        )
    dimensions["headings"] = heading_coverage

    content = _coverage(_strings(annotations.get("content_samples")), all_text)
    content["duplication_ratio"] = _duplication_ratio(blocks)
    if content["expected_count"]:
        content["score"] = round(
            content["score"] * (1 - content["duplication_ratio"]),
            4,
        )
    dimensions["content"] = content

    dimensions["figures"] = _element_coverage(
        annotations.get("figures"),
        [block for block in blocks if block.get("type") == "image"],
        required_fields=("caption_terms", "factual_terms"),
        require_alt_text=True,
    )
    dimensions["tables"] = _element_coverage(
        annotations.get("tables"),
        [block for block in blocks if block.get("type") == "table"],
        required_fields=("caption_terms", "header_terms"),
    )
    dimensions["formulas"] = _element_coverage(
        annotations.get("formulas"),
        [
            block
            for block in blocks
            if block.get("type") in {"formula", "equation", "math"}
            or any(
                key in _normalized_text(block)
                for key in ("latex", "formula", "equation")
            )
        ],
        required_fields=("source_terms", "verbalization_terms"),
    )
    reference_terms: list[str] = []
    for reference in _dicts(annotations.get("references")):
        reference_terms.extend(_strings(reference.get("entry_terms")))
        reference_terms.extend(_strings(reference.get("callout_terms")))
    dimensions["references"] = _coverage(reference_terms, all_text)
    dimensions["contract"] = _contract_quality(document)

    scored = [
        value["score"]
        for value in dimensions.values()
        if value.get("applicable", True)
    ]
    overall = round(100 * sum(scored) / len(scored), 2) if scored else 0.0
    return {
        "score": overall,
        "dimensions": dimensions,
        "applicable_dimensions": len(scored),
        "metric_version": "1.0.0",
    }


def _coverage(expected: list[str], actual_text: str) -> dict[str, Any]:
    expected = [item for item in expected if item.strip()]
    actual = _normalize(actual_text)
    matched = [item for item in expected if _matches(item, actual)]
    missing = [item for item in expected if item not in matched]
    applicable = bool(expected)
    return {
        "score": round(len(matched) / len(expected), 4) if applicable else 0.0,
        "applicable": applicable,
        "expected_count": len(expected),
        "matched_count": len(matched),
        "matched": matched,
        "missing": missing,
    }


def _element_coverage(
    expected_items: Any,
    actual_blocks: list[dict[str, Any]],
    *,
    required_fields: tuple[str, ...],
    require_alt_text: bool = False,
) -> dict[str, Any]:
    expected = _dicts(expected_items)
    matched: list[str] = []
    missing: list[str] = []
    used_indexes: set[int] = set()

    for index, item in enumerate(expected, start=1):
        terms = [
            term
            for field in required_fields
            for term in _strings(item.get(field))
        ]
        label = str(item.get("id") or item.get("label") or index)
        found_index = next(
            (
                block_index
                for block_index, block in enumerate(actual_blocks)
                if block_index not in used_indexes
                and all(_matches(term, _normalized_text(block)) for term in terms)
                and (
                    not require_alt_text
                    or bool(str(block.get("alt_text", "")).strip())
                )
            ),
            None,
        )
        if found_index is None:
            missing.append(label)
        else:
            used_indexes.add(found_index)
            matched.append(label)

    applicable = bool(expected)
    return {
        "score": round(len(matched) / len(expected), 4) if applicable else 0.0,
        "applicable": applicable,
        "expected_count": len(expected),
        "matched_count": len(matched),
        "matched": matched,
        "missing": missing,
        "actual_count": len(actual_blocks),
    }


def _contract_quality(document: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "schema_version": bool(document.get("schema_version")),
        "language": bool(document.get("language")),
        "sections": isinstance(document.get("sections"), list)
        and bool(document["sections"]),
        "semantic_headings": document.get("accessibility", {}).get(
            "semantic_headings"
        )
        is True,
        "navigation": document.get("accessibility", {}).get("navigation") is True,
    }
    passed = [name for name, result in checks.items() if result]
    failed = [name for name, result in checks.items() if not result]
    return {
        "score": round(len(passed) / len(checks), 4),
        "applicable": True,
        "expected_count": len(checks),
        "matched_count": len(passed),
        "matched": passed,
        "missing": failed,
    }


def _heading_texts(
    document: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> list[str]:
    headings = [
        str(block.get("text") or block.get("title") or "")
        for block in blocks
        if block.get("type") == "heading"
    ]
    if headings:
        return headings
    return [
        str(section.get("title", ""))
        for section in _walk_sections(document.get("sections", []))
        if section.get("title")
    ]


def _order_accuracy(expected: list[str], actual: list[str]) -> float:
    if len(expected) < 2:
        return 1.0 if expected else 0.0
    positions: list[int] = []
    for item in expected:
        position = next(
            (
                index
                for index, candidate in enumerate(actual)
                if _matches(item, _normalize(candidate))
            ),
            -1,
        )
        positions.append(position)
    pairs = list(zip(positions, positions[1:]))
    correct = sum(1 for left, right in pairs if left >= 0 and right > left)
    return round(correct / len(pairs), 4)


def _duplication_ratio(blocks: list[dict[str, Any]]) -> float:
    texts = [
        _normalize(str(block.get("text", "")))
        for block in blocks
        if len(_normalize(str(block.get("text", "")))) >= 20
    ]
    if not texts:
        return 0.0
    return round(1 - len(set(texts)) / len(texts), 4)


def _walk_sections(raw_sections: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(raw_sections, list):
        return
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        yield section
        yield from _walk_sections(section.get("children", []))


def _walk_blocks(raw_sections: Any) -> Iterable[dict[str, Any]]:
    for section in _walk_sections(raw_sections):
        blocks = section.get("blocks", [])
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, dict):
                    yield block


def _normalized_text(value: Any) -> str:
    strings: list[str] = []

    def collect(item: Any) -> None:
        if isinstance(item, str):
            strings.append(item)
        elif isinstance(item, dict):
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    return _normalize("\n".join(strings))


def _matches(expected: str, normalized_actual: str) -> bool:
    normalized_expected = _normalize(expected)
    if not normalized_expected:
        return False
    return normalized_expected in normalized_actual


def _normalize(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.casefold()).strip()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]