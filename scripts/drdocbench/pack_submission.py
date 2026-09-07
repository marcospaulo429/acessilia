"""Valida um predictions.jsonl contra o split test e gera submission.zip.

Uso:
    python scripts/drdocbench/pack_submission.py predictions.jsonl \
        [--root var/data/drdocbench] [--out var/submissions/<nome>.zip] [--allow-empty]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.benchmarks.drdocbench.submission import (  # noqa: E402
    expected_test_ids,
    pack_submission,
    read_jsonl,
    validate_predictions,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--root", type=Path, default=Path("var/data/drdocbench"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--allow-empty", action="store_true", help="nao falha se houver markdown vazio")
    args = parser.parse_args(argv)

    records = read_jsonl(args.jsonl)
    report = validate_predictions(records, expected_test_ids(args.root))
    print(report.summary())
    if not report.ok:
        return 2
    if report.empty_markdown and not args.allow_empty:
        print("ha paginas com markdown vazio; use --allow-empty para prosseguir")
        return 3

    out = args.out or Path("var/submissions") / f"{datetime.now(UTC):%Y%m%d-%H%M}-{args.jsonl.stem}.zip"
    pack_submission(args.jsonl, out)
    print(f"submission: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
