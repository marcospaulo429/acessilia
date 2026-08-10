from pathlib import Path

import pytest

from backend.pipeline.scientific.detector import (
    detect_document_profile,
    detect_profile_from_text,
)


SCIENTIFIC_TEXT = """
Abstract
We evaluate a reproducible method for document understanding.
Keywords: accessibility, scientific documents
1 Introduction
The baseline follows prior work (Silva et al., 2024).
2 Methods
Figure 1
Table 1
3 Results
The results reproduce earlier observations (Souza et al., 2023).
4 Discussion
The limitations agree with another study (Lima et al., 2022).
5 Conclusion
References
[1] Silva, A. Example reference.
[2] Souza, B. Another reference.
[3] Lima, C. Final reference.
"""


def test_detects_scientific_text_from_multiple_independent_signals():
    profile = detect_profile_from_text(
        SCIENTIFIC_TEXT,
        metadata={"title": "A Study", "author": "A. Silva"},
    )

    assert profile.effective_profile == "scientific"
    assert profile.decision_source == "detector"
    assert "abstract-heading" in profile.evidence
    assert "reference-section" in profile.evidence


def test_does_not_classify_general_report_from_generic_headings_only():
    profile = detect_profile_from_text(
        "Introducao\nEste relatorio apresenta a equipe.\nConclusao\nProximos passos."
    )

    assert profile.effective_profile == "general"


@pytest.mark.parametrize("requested", ["scientific", "general"])
def test_explicit_profile_overrides_detection(requested: str):
    profile = detect_document_profile(
        Path("not-a-real-file.pdf"),
        requested_profile=requested,  # type: ignore[arg-type]
    )

    assert profile.effective_profile == requested
    assert profile.decision_source == "override"
    assert profile.confidence == 1.0


def test_non_pdf_defaults_to_general_without_reading_file():
    profile = detect_document_profile(Path("image.png"))

    assert profile.effective_profile == "general"
    assert profile.decision_source == "unsupported"


def test_rejects_invalid_requested_profile():
    with pytest.raises(ValueError, match="document_profile invalido"):
        detect_document_profile(
            Path("paper.pdf"),
            requested_profile="invalid",  # type: ignore[arg-type]
        )