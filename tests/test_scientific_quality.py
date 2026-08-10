from backend.pipeline.scientific.quality import evaluate_scientific_quality


ANNOTATIONS = {
    "title": "Graph Reasoning for Science",
    "headings": ["Abstract", "Methods", "Results"],
    "content_samples": ["five benchmark datasets", "accuracy improved"],
    "figures": [
        {
            "id": "fig-1",
            "caption_terms": ["Figure 1"],
            "factual_terms": ["accuracy increases"],
        }
    ],
    "tables": [
        {
            "id": "table-1",
            "caption_terms": ["Table 1"],
            "header_terms": ["Model", "Accuracy"],
        }
    ],
    "formulas": [
        {
            "id": "eq-1",
            "source_terms": ["x + y"],
            "verbalization_terms": ["x plus y"],
        }
    ],
    "references": [
        {"entry_terms": ["Smith 2024"], "callout_terms": ["[1]"]}
    ],
}


def _document(*, complete: bool) -> dict:
    blocks = [
        {"type": "heading", "text": "Abstract"},
        {
            "type": "paragraph",
            "text": "We evaluate five benchmark datasets.",
        },
        {"type": "heading", "text": "Methods"},
    ]
    if complete:
        blocks.extend(
            [
                {
                    "type": "image",
                    "caption": "Figure 1",
                    "alt_text": "The graph shows that accuracy increases.",
                },
                {
                    "type": "table",
                    "table_ast": {
                        "caption": "Table 1",
                        "header": [
                            {
                                "cells": [
                                    {"text": "Model"},
                                    {"text": "Accuracy"},
                                ]
                            }
                        ],
                    },
                },
                {
                    "type": "formula",
                    "latex": "x + y",
                    "verbalization": "x plus y",
                },
                {"type": "heading", "text": "Results"},
                {
                    "type": "paragraph",
                    "text": "Accuracy improved. See [1]. Smith 2024.",
                },
            ]
        )
    return {
        "schema_version": "1.0.0",
        "title": "Graph Reasoning for Science",
        "language": "en",
        "accessibility": {"semantic_headings": True, "navigation": True},
        "sections": [{"title": "Paper", "blocks": blocks, "children": []}],
    }


def test_complete_scientific_document_scores_all_dimensions():
    result = evaluate_scientific_quality(_document(complete=True), ANNOTATIONS)

    assert result["score"] == 100.0
    assert all(
        dimension["score"] == 1.0
        for dimension in result["dimensions"].values()
        if dimension["applicable"]
    )


def test_degraded_document_scores_lower_and_reports_missing_evidence():
    complete = evaluate_scientific_quality(_document(complete=True), ANNOTATIONS)
    degraded = evaluate_scientific_quality(_document(complete=False), ANNOTATIONS)

    assert degraded["score"] < complete["score"] - 40
    assert degraded["dimensions"]["figures"]["missing"] == ["fig-1"]
    assert degraded["dimensions"]["tables"]["missing"] == ["table-1"]
    assert degraded["dimensions"]["formulas"]["missing"] == ["eq-1"]