"""Testes do empacotador/validador de submissao Dr.DocBench."""

from __future__ import annotations

import zipfile
from pathlib import Path

from backend.benchmarks.drdocbench.dataset import PageId
from backend.benchmarks.drdocbench.submission import (
    pack_submission,
    prediction_record,
    read_jsonl,
    validate_predictions,
    write_jsonl,
)

IDS = [PageId("MEDICAL", "doc-a", 7), PageId("MEDICAL", "doc-a", 8), PageId("LAW", "doc-b", 3)]


def test_validate_ok() -> None:
    records = [prediction_record(p, "# ok") for p in IDS]
    report = validate_predictions(records, IDS)
    assert report.ok
    assert report.expected == report.found == 3
    assert report.empty_markdown == []


def test_validate_detects_missing_extra_duplicated_malformed_empty() -> None:
    records = [
        prediction_record(IDS[0], "x"),
        prediction_record(IDS[0], "y"),  # duplicada
        prediction_record(PageId("LAW", "doc-b", 99), "z"),  # extra
        {"subject": "LAW", "document_id": "doc-b", "page": "not-int", "markdown": "q"},  # malformada
        prediction_record(IDS[2], "   "),  # vazia
    ]
    report = validate_predictions(records, IDS)
    assert not report.ok
    assert report.missing == ["MEDICAL/doc-a/8"]
    assert report.extra == ["LAW/doc-b/99"]
    assert report.duplicated == ["MEDICAL/doc-a/7"]
    assert report.malformed == ["linha 3"]
    assert report.empty_markdown == ["LAW/doc-b/3"]
    assert "missing: 1" in report.summary()


def test_jsonl_roundtrip_and_zip(tmp_path: Path) -> None:
    records = [prediction_record(p, "texto com acento: ação") for p in IDS]
    jsonl = write_jsonl(records, tmp_path / "pred.jsonl")
    assert read_jsonl(jsonl) == records
    zip_path = pack_submission(jsonl, tmp_path / "sub.zip")
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["predictions.jsonl"]
        assert "ação" in zf.read("predictions.jsonl").decode("utf-8")
