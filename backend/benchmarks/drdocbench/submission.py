"""Empacota e valida predicoes para o EvalAI (Dr.DocBench).

Formato: ``submission.zip`` contendo ``predictions.jsonl`` com uma linha por pagina
de ``test/``: ``{"subject", "document_id", "page", "markdown"}``. O avaliador rejeita
predicoes faltantes, extras, duplicadas ou com identificadores invalidos.
"""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from backend.benchmarks.drdocbench.dataset import DrDocBenchDataset, PageId

REQUIRED_FIELDS = ("subject", "document_id", "page", "markdown")


@dataclass
class ValidationReport:
    expected: int
    found: int
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    duplicated: list[str] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)
    empty_markdown: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.extra or self.duplicated or self.malformed)

    def summary(self) -> str:
        lines = [f"esperadas={self.expected} encontradas={self.found} ok={self.ok}"]
        for name in ("missing", "extra", "duplicated", "malformed", "empty_markdown"):
            items = getattr(self, name)
            if items:
                lines.append(f"  {name}: {len(items)} (ex.: {items[:3]})")
        return "\n".join(lines)


def prediction_record(page_id: PageId, markdown: str) -> dict[str, object]:
    return {
        "subject": page_id.subject,
        "document_id": page_id.document_id,
        "page": page_id.page,
        "markdown": markdown,
    }


def _key(record: Mapping[str, object]) -> str | None:
    try:
        return PageId(str(record["subject"]), str(record["document_id"]), int(record["page"])).key  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError):
        return None


def validate_predictions(
    records: Iterable[Mapping[str, object]], expected_ids: Iterable[PageId]
) -> ValidationReport:
    expected = {p.key for p in expected_ids}
    seen: Counter[str] = Counter()
    malformed: list[str] = []
    empty: list[str] = []
    for i, rec in enumerate(records):
        if not all(f in rec for f in REQUIRED_FIELDS) or not isinstance(rec.get("markdown"), str):
            malformed.append(f"linha {i}")
            continue
        key = _key(rec)
        if key is None:
            malformed.append(f"linha {i}")
            continue
        seen[key] += 1
        if not str(rec["markdown"]).strip():
            empty.append(key)
    found = set(seen)
    return ValidationReport(
        expected=len(expected),
        found=sum(seen.values()),
        missing=sorted(expected - found),
        extra=sorted(found - expected),
        duplicated=sorted(k for k, n in seen.items() if n > 1),
        malformed=malformed,
        empty_markdown=sorted(empty),
    )


def write_jsonl(records: Iterable[Mapping[str, object]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def read_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def pack_submission(jsonl_path: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path, arcname="predictions.jsonl")
    return zip_path


def expected_test_ids(dataset_root: Path) -> list[PageId]:
    return DrDocBenchDataset(dataset_root, "test", load_gt=False).page_ids()
