from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from benchmark_pipelines import run_benchmark
except ModuleNotFoundError:  # importado como modulo a partir da raiz do projeto
    from scripts.benchmark_pipelines import run_benchmark


def aggregate_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(reports),
        "engines": {},
        "paired_success_count": 0,
        "verdict": "inconclusive",
    }
    for engine_name in ("legacy", "pddl"):
        successful = [
            report["engines"][engine_name]
            for report in reports
            if report.get("engines", {}).get(engine_name, {}).get("status") == "ok"
        ]
        scores = [
            engine["quality"]["score"]
            for engine in successful
            if isinstance(engine.get("quality"), dict)
        ]
        elapsed = [engine["elapsed_ms"] for engine in successful]
        dimensions: dict[str, float] = {}
        dimension_names = {
            name
            for engine in successful
            for name, value in engine.get("quality", {}).get("dimensions", {}).items()
            if value.get("applicable", True)
        }
        for name in sorted(dimension_names):
            values = [
                engine["quality"]["dimensions"][name]["score"] * 100
                for engine in successful
                if name in engine.get("quality", {}).get("dimensions", {})
                and engine["quality"]["dimensions"][name].get("applicable", True)
            ]
            if values:
                dimensions[name] = round(statistics.fmean(values), 2)
        aggregate["engines"][engine_name] = {
            "success_count": len(successful),
            "failure_count": len(reports) - len(successful),
            "quality_mean": round(statistics.fmean(scores), 2) if scores else None,
            "quality_stddev": round(statistics.pstdev(scores), 2)
            if len(scores) > 1
            else 0.0
            if scores
            else None,
            "elapsed_ms_mean": round(statistics.fmean(elapsed)) if elapsed else None,
            "dimensions": dimensions,
        }

    paired = [
        report
        for report in reports
        if all(
            report.get("engines", {}).get(engine, {}).get("status") == "ok"
            and isinstance(
                report.get("engines", {}).get(engine, {}).get("quality"), dict
            )
            for engine in ("legacy", "pddl")
        )
    ]
    aggregate["paired_success_count"] = len(paired)
    if paired:
        deltas = [
            report["engines"]["pddl"]["quality"]["score"]
            - report["engines"]["legacy"]["quality"]["score"]
            for report in paired
        ]
        mean_delta = round(statistics.fmean(deltas), 2)
        aggregate["quality_score_delta_pddl_minus_legacy_mean"] = mean_delta
        aggregate["verdict"] = (
            "pddl" if mean_delta > 0 else "legacy" if mean_delta < 0 else "tie"
        )
    return aggregate


async def run_corpus_benchmark(
    manifest_path: Path,
    corpus_dir: Path,
    output_dir: Path,
    *,
    repetitions: int,
    mode: str,
    extractor_backend: str,
    export_formats: list[str],
) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    papers = manifest.get("papers")
    if not isinstance(papers, list) or not papers:
        raise ValueError("manifesto sem papers")

    reports: list[dict[str, Any]] = []
    for paper in papers:
        paper_id = paper["id"]
        pdf_path = corpus_dir / f"{paper_id}.pdf"
        annotation_path = manifest_path.parent / paper["annotations"]
        annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
        for repetition in range(1, repetitions + 1):
            run_dir = output_dir / paper_id / f"run-{repetition}"
            report_path = await run_benchmark(
                file_path=pdf_path,
                output_dir=run_dir,
                mode=mode,
                export_formats=export_formats,
                pddl_extractor_backend=extractor_backend,
                annotations=annotations,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["paper_id"] = paper_id
            report["repetition"] = repetition
            reports.append(report)

    output_dir.mkdir(parents=True, exist_ok=True)
    aggregate = aggregate_reports(reports)
    aggregate.update(
        {
            "schema_version": "1.0.0",
            "manifest": str(manifest_path.resolve()),
            "repetitions": repetitions,
            "papers": len(papers),
            "reports": reports,
        }
    )
    output_path = output_dir / "scientific_benchmark_report.json"
    output_path.write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara qualidade, tempo e custo nominal no corpus científico."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/scientific_papers/corpus.json"),
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("var/data/scientific-benchmark"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("var/data/scientific-benchmark-results"),
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--mode", choices=["normal", "medio", "detalhado"], default="normal")
    parser.add_argument(
        "--pddl-extractor-backend",
        choices=["pymupdf", "docling"],
        default="docling",
    )
    parser.add_argument("--export-formats", default="txt")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repetitions < 1:
        print("Erro: repetitions deve ser pelo menos 1")
        return 1
    export_formats = [
        item.strip().lower()
        for item in args.export_formats.split(",")
        if item.strip()
    ]
    try:
        report_path = asyncio.run(
            run_corpus_benchmark(
                args.manifest.resolve(),
                args.corpus_dir.resolve(),
                args.output_dir.resolve(),
                repetitions=args.repetitions,
                mode=args.mode,
                extractor_backend=args.pddl_extractor_backend,
                export_formats=export_formats,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}")
        return 1
    print(f"Relatório agregado: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())