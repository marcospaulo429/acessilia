from __future__ import annotations

import re

from backend.core.manifest.models import (
    ManifestElement,
    Obligation,
    Observation,
    ProcessingManifest,
)


_FIGURE_CAPTION_RE = re.compile(
    r"^\s*(fig(?:ure|ura)?\.?\s*\d+[a-z]?)\s*[:.\-–]?\s*",
    re.IGNORECASE,
)
_TABLE_CAPTION_RE = re.compile(
    r"^\s*((?:table|tabela)\s+\d+[a-z]?)\s*[:.\-–]?\s*",
    re.IGNORECASE,
)


def enrich_scientific_manifest(manifest: ProcessingManifest) -> None:
    enrich_scientific_elements(manifest.elements)
    observations, obligations = derive_scientific_processing_needs(manifest.elements)

    known_observations = {item.id for item in manifest.observations}
    manifest.observations.extend(
        item for item in observations if item.id not in known_observations
    )
    known_obligations = {item.id for item in manifest.obligations}
    manifest.obligations.extend(
        item for item in obligations if item.id not in known_obligations
    )
    apply_scientific_dependencies(manifest)
    manifest.summary.observation_count = len(manifest.observations)
    manifest.summary.obligation_count = len(manifest.obligations)


def enrich_scientific_elements(elements: list[ManifestElement]) -> None:
    ordered = sorted(elements, key=lambda item: item.reading_order)
    current_section: ManifestElement | None = None
    for element in ordered:
        if element.type in {"title", "heading"}:
            current_section = element
        elif current_section is not None:
            element.metadata["scientific_section"] = {
                "element_id": current_section.id,
                "title": current_section.text or "",
                "level": current_section.hierarchy_level,
            }

    captions = [element for element in ordered if _caption_kind(element) is not None]
    targets = [element for element in ordered if element.type in {"picture", "table"}]
    for target in targets:
        caption = _nearest_compatible_caption(target, captions)
        if caption is None:
            continue
        kind, label = _caption_kind(caption) or (None, None)
        if kind is None or label is None:
            continue
        target.metadata["scientific_caption"] = {
            "element_id": caption.id,
            "label": label,
            "text": caption.text or "",
        }
        caption.metadata["scientific_target"] = {
            "element_id": target.id,
            "type": target.type,
        }


def derive_scientific_processing_needs(
    elements: list[ManifestElement],
) -> tuple[list[Observation], list[Obligation]]:
    observations: list[Observation] = []
    obligations: list[Obligation] = []

    for element in elements:
        if element.type not in {"picture", "table"}:
            continue
        suffix = element.id.removeprefix("element-")
        caption = element.metadata.get("scientific_caption")
        if isinstance(caption, dict):
            obligation_id = f"obligation-link-caption-{suffix}"
            observations.append(
                Observation(
                    id=f"observation-link-caption-{suffix}",
                    kind="scientific-caption-link",
                    severity="info",
                    message="O elemento científico deve preservar sua legenda associada.",
                    target_ids=[element.id, str(caption["element_id"])],
                    evidence={"caption_label": caption.get("label")},
                )
            )
            obligations.append(
                Obligation(
                    id=obligation_id,
                    kind="link-scientific-caption",
                    target_ids=[element.id, str(caption["element_id"])],
                    admissible_methods=["deterministic-caption-link"],
                    method_costs={"deterministic-caption-link": 1},
                    rationale="A figura ou tabela deve manter uma ligação verificável com sua legenda.",
                )
            )

    return observations, obligations


def apply_scientific_dependencies(manifest: ProcessingManifest) -> None:
    obligation_by_id = {item.id: item for item in manifest.obligations}
    for element in manifest.elements:
        caption = element.metadata.get("scientific_caption")
        if element.type not in {"picture", "table"} or not isinstance(caption, dict):
            continue
        suffix = element.id.removeprefix("element-")
        link_id = f"obligation-link-caption-{suffix}"
        processing_kind = "describe-image" if element.type == "picture" else "linearize-table"
        processing = obligation_by_id.get(f"obligation-{processing_kind}-{suffix}")
        if processing is not None and link_id not in processing.dependencies:
            processing.dependencies.append(link_id)


def _caption_kind(element: ManifestElement) -> tuple[str, str] | None:
    text = (element.text or "").strip()
    figure_match = _FIGURE_CAPTION_RE.match(text)
    if figure_match:
        return "picture", figure_match.group(1)
    table_match = _TABLE_CAPTION_RE.match(text)
    if table_match:
        return "table", table_match.group(1)
    return None


def _nearest_compatible_caption(
    target: ManifestElement,
    captions: list[ManifestElement],
) -> ManifestElement | None:
    candidates = []
    for caption in captions:
        caption_kind = _caption_kind(caption)
        if caption_kind is None or caption_kind[0] != target.type:
            continue
        if target.page_number != caption.page_number:
            continue
        distance = abs(target.reading_order - caption.reading_order)
        if distance <= 3:
            candidates.append((distance, caption.reading_order, caption))
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1]))[2]