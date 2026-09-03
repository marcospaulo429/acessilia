"""Benchmark A/B/C do replanejamento PDDL sobre o acessilia-dataset.

Compara três braços em execução live:
  A (original)   — uma passada, sem replanejamento e sem llm-verbalizer;
  B (replan)     — loop de replanejamento, sem llm-verbalizer;
  C (replan+llm) — loop de replanejamento com a cascata completa.

Sem injeção de falha, documentos "fáceis" não exercitam o replanejamento e
os braços tendem a empatar; use --inject-failure para sabotar métodos e
medir a taxa de recuperação automática de cada braço.

Ferramenta de diagnóstico manual; não é teste automatizado.

Exemplos:
  python scripts/benchmark_replanning.py --max-docs 2 --extractor-backend pymupdf
  python scripts/benchmark_replanning.py --inject-failure mathml
  python scripts/benchmark_replanning.py --arms A C --inject-failure mathml latex-verbalizer --mock-llm "E=mc^2"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.agents import pddl_orchestrator as pddl_module
from backend.agents.pddl_orchestrator import PddlAccessibilityOrchestrator
from backend.core.execution.models import MethodResult

SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

ARMS: dict[str, dict[str, Any]] = {
    "A": {
        "label": "original (1 passada, sem LLM)",
        "max_replans": 0,
        "unavailable_methods": ("llm-verbalizer",),
    },
    "B": {
        "label": "replanejamento (sem LLM)",
        "max_replans": 8,
        "unavailable_methods": ("llm-verbalizer",),
    },
    "C": {
        "label": "replanejamento + llm-verbalizer",
        "max_replans": 8,
        "unavailable_methods": (),
    },
}


def _inject_failures(
    orchestrator: PddlAccessibilityOrchestrator,
    methods: list[str],
    fail_count: int,
) -> None:
    """Sabota handlers para falharem nas primeiras ``fail_count`` chamadas.

    ``fail_count`` <= 0 significa falhar sempre.
    """
    registry = orchestrator.executor.registry
    for method in methods:
        original = registry.get(method)
        if original is None:
            continue
        calls = {"n": 0}

        def sabotaged(
            manifest: Any,
            obligation_id: str,
            _original=original,
            _calls=calls,
            _method=method,
        ) -> MethodResult:
            _calls["n"] += 1
            if fail_count <= 0 or _calls["n"] <= fail_count:
                return MethodResult(
                    success=False,
                    validated=False,
                    message=f"Falha injetada pelo benchmark ({_method})",
                )
            return _original(manifest, obligation_id)

        registry.register(method, sabotaged)


def _count_formula_blocks(payload: dict[str, Any]) -> dict[str, int]:
    total = 0
    with_mathml = 0
    with_verbalization = 0
    for page in payload.get("pages", []):
        for block in page.get("blocks", []):
            metadata = block.get("metadata") or {}
            if metadata.get("raw_label") != "formula":
                continue
            total += 1
            if metadata.get("mathml"):
                with_mathml += 1
            if metadata.get("verbalization"):
                with_verbalization += 1
    return {
        "total": total,
        "with_mathml": with_mathml,
        "with_verbalization": with_verbalization,
    }


async def _run_document(
    document: Path,
    arm: str,
    args: argparse.Namespace,
    tmpdir: Path,
) -> dict[str, Any]:
    config = ARMS[arm]
    orchestrator = PddlAccessibilityOrchestrator(
        planner_backend=args.planner_backend,
        execute_dry_run=False,
        execute_live=True,
        max_replans=config["max_replans"],
        unavailable_methods=config["unavailable_methods"],
        extractor_backend=args.extractor_backend,
        enable_ocr=not args.disable_ocr,
    )
    if args.inject_failure:
        _inject_failures(orchestrator, args.inject_failure, args.inject_count)

    llm_calls = {"n": 0}
    original_propose = pddl_module._propose_formula_latex_via_llm

    def counting_propose(image_bytes: bytes, page_num: int) -> str:
        llm_calls["n"] += 1
        return original_propose(image_bytes, page_num)

    pddl_module._propose_formula_latex_via_llm = counting_propose
    started = time.perf_counter()
    try:
        payload = await orchestrator.executar(
            document,
            tmpdir,
            mode=args.mode,
            structured_output=True,
        )
    finally:
        pddl_module._propose_formula_latex_via_llm = original_propose
    elapsed = time.perf_counter() - started

    execution = payload.get("pddl_execution") or {}
    metadata = payload.get("canonical_metadata") or {}
    obligations = execution.get("obligations") or {}
    metrics = execution.get("metrics") or {}
    total_obligations = sum(obligations.values())
    satisfied = obligations.get("satisfied", 0)
    human = metrics.get("human_review_obligations", 0)
    formulas = _count_formula_blocks(payload)
    llm_winners = (metrics.get("winner_by_method") or {}).get(
        "llm-verbalizer", 0
    )
    return {
        "arm": arm,
        "document": document.name,
        "elapsed_seconds": round(elapsed, 2),
        "execution_status": execution.get("status"),
        "replans": execution.get("replans", 0),
        "failure": execution.get("failure"),
        "obligations": obligations,
        "obligations_total": total_obligations,
        "obligations_satisfied": satisfied,
        "auto_satisfaction_rate": (
            round((satisfied - human) / total_obligations, 4)
            if total_obligations
            else None
        ),
        "human_review_rate": (
            round(human / total_obligations, 4) if total_obligations else None
        ),
        "recovered_obligations": metrics.get("recovered_obligations", 0),
        "failed_attempts": metrics.get("failed_attempts", 0),
        "winner_by_method": metrics.get("winner_by_method", {}),
        "by_kind": metrics.get("by_kind", {}),
        "initial_expected_cost": execution.get("initial_expected_cost"),
        "final_expected_cost": execution.get("final_expected_cost"),
        "executed_cost": metrics.get("executed_cost", 0),
        "wasted_cost": metrics.get("wasted_cost", 0),
        "plan_steps": execution.get("plan_steps"),
        "timings": execution.get("timings"),
        "llm_calls": llm_calls["n"],
        "llm_accepted": llm_winners,
        "llm_acceptance_rate": (
            round(llm_winners / llm_calls["n"], 4) if llm_calls["n"] else None
        ),
        "expected_total_cost": metadata.get("pddl_expected_total_cost"),
        "formulas": formulas,
        "technical_warnings": payload.get("technical_warnings", []),
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for arm in sorted({item["arm"] for item in results}):
        arm_results = [item for item in results if item["arm"] == arm]
        completed = [
            item for item in arm_results if item["execution_status"] == "completed"
        ]
        rates = [
            item["auto_satisfaction_rate"]
            for item in arm_results
            if item.get("auto_satisfaction_rate") is not None
        ]
        human_rates = [
            item["human_review_rate"]
            for item in arm_results
            if item.get("human_review_rate") is not None
        ]
        formulas_total = sum(item["formulas"]["total"] for item in arm_results)
        formulas_ok = sum(
            item["formulas"]["with_verbalization"] for item in arm_results
        )
        llm_calls = sum(item.get("llm_calls", 0) for item in arm_results)
        llm_accepted = sum(item.get("llm_accepted", 0) for item in arm_results)
        planning_times = [
            (item.get("timings") or {}).get("planning_execution_seconds")
            for item in arm_results
        ]
        planning_times = [value for value in planning_times if value is not None]
        errors = [item for item in arm_results if item.get("error")]
        summary[arm] = {
            "label": ARMS[arm]["label"],
            "documents": len(arm_results),
            "completed": len(completed),
            "errors": len(errors),
            "mean_replans": round(
                sum(item["replans"] or 0 for item in arm_results)
                / max(1, len(arm_results)),
                2,
            ),
            "mean_auto_satisfaction_rate": (
                round(sum(rates) / len(rates), 4) if rates else None
            ),
            "mean_human_review_rate": (
                round(sum(human_rates) / len(human_rates), 4)
                if human_rates
                else None
            ),
            "recovered_obligations": sum(
                item.get("recovered_obligations", 0) for item in arm_results
            ),
            "failed_attempts": sum(
                item.get("failed_attempts", 0) for item in arm_results
            ),
            "wasted_cost": sum(item.get("wasted_cost", 0) for item in arm_results),
            "executed_cost": sum(
                item.get("executed_cost", 0) for item in arm_results
            ),
            "llm_calls": llm_calls,
            "llm_accepted": llm_accepted,
            "llm_acceptance_rate": (
                round(llm_accepted / llm_calls, 4) if llm_calls else None
            ),
            "formulas_total": formulas_total,
            "formulas_verbalized": formulas_ok,
            "mean_elapsed_seconds": round(
                sum(item["elapsed_seconds"] or 0 for item in arm_results)
                / max(1, len(arm_results)),
                2,
            ),
            "mean_planning_execution_seconds": (
                round(sum(planning_times) / len(planning_times), 3)
                if planning_times
                else None
            ),
        }
    return summary


async def _main_async(args: argparse.Namespace) -> dict[str, Any]:
    input_dir = Path(args.input_dir)
    documents = sorted(
        item
        for item in input_dir.iterdir()
        if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if args.max_docs:
        documents = documents[: args.max_docs]
    if not documents:
        raise SystemExit(f"Nenhum documento suportado em {input_dir}")

    if args.mock_llm is not None:
        pddl_module._propose_formula_latex_via_llm = (
            lambda _image, _page, _latex=args.mock_llm: _latex
        )

    if args.skip_enrichment:
        # Enriquecimento (VisionAgent/DataAgent) e identico nos tres bracos e
        # depende de LLM externa; pular evita minutos de timeout por imagem.
        async def _noop_enrich(*_args: Any, **_kwargs: Any) -> None:
            return None

        pddl_module._enrich_picture_descriptions = _noop_enrich
        pddl_module._enrich_table_structures = _noop_enrich

    tmpdir = Path(args.tmpdir)
    tmpdir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for document in documents:
        for arm in args.arms:
            print(f"[{arm}] {document.name} ...", flush=True)
            try:
                result = await _run_document(document, arm, args, tmpdir)
            except Exception as exc:  # ferramenta de diagnóstico: registra e segue
                result = {
                    "arm": arm,
                    "document": document.name,
                    "error": f"{type(exc).__name__}: {exc}",
                    "execution_status": None,
                    "replans": 0,
                    "elapsed_seconds": None,
                    "auto_satisfaction_rate": None,
                    "formulas": {
                        "total": 0,
                        "with_mathml": 0,
                        "with_verbalization": 0,
                    },
                }
            results.append(result)
            status = result.get("execution_status") or result.get("error")
            print(
                f"[{arm}] {document.name}: {status} "
                f"(replans={result.get('replans')}, "
                f"satisf.={result.get('auto_satisfaction_rate')})",
                flush=True,
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "input_dir": str(input_dir),
            "arms": args.arms,
            "inject_failure": args.inject_failure,
            "inject_count": args.inject_count,
            "mock_llm": args.mock_llm,
            "extractor_backend": args.extractor_backend,
            "planner_backend": args.planner_backend,
            "mode": args.mode,
        },
        "summary": _aggregate(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        default="third_party/acessilia-dataset/input",
        help="Diretório com os documentos do benchmark",
    )
    parser.add_argument(
        "--output-dir",
        default="var/data/benchmarks",
        help="Diretório de saída do relatório JSON",
    )
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=sorted(ARMS),
        default=["A", "B", "C"],
        help="Braços do experimento a executar",
    )
    parser.add_argument(
        "--inject-failure",
        nargs="+",
        default=[],
        metavar="METHOD",
        help="Métodos sabotados para falhar (ex.: mathml latex-verbalizer)",
    )
    parser.add_argument(
        "--inject-count",
        type=int,
        default=0,
        help="Falha apenas nas N primeiras chamadas por método (0 = sempre)",
    )
    parser.add_argument(
        "--mock-llm",
        default=None,
        metavar="LATEX",
        help="Substitui a LLM por uma resposta fixa (teste offline do braço C)",
    )
    parser.add_argument(
        "--extractor-backend",
        choices=["docling", "pymupdf"],
        default="docling",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Pula o enriquecimento visual/OCR pre-planejamento (igual nos 3 bracos)",
    )
    parser.add_argument("--planner-backend", default="internal")
    parser.add_argument("--mode", default="medio")
    parser.add_argument("--disable-ocr", action="store_true")
    parser.add_argument("--max-docs", type=int, default=0)
    parser.add_argument("--tmpdir", default="var/temp/benchmark-replanning")
    args = parser.parse_args()

    report = asyncio.run(_main_async(args))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"replanning-{timestamp}.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\n=== Resumo por braço ===")
    for arm, summary in report["summary"].items():
        print(
            f"{arm} [{summary['label']}]: "
            f"{summary['completed']}/{summary['documents']} completos, "
            f"replans médio={summary['mean_replans']}, "
            f"satisfação automática={summary['mean_auto_satisfaction_rate']}, "
            f"escalonamento humano={summary['mean_human_review_rate']}, "
            f"recuperadas={summary['recovered_obligations']}, "
            f"custo desperdiçado={summary['wasted_cost']}, "
            f"LLM={summary['llm_accepted']}/{summary['llm_calls']}, "
            f"fórmulas verbalizadas={summary['formulas_verbalized']}"
            f"/{summary['formulas_total']}, "
            f"tempo médio={summary['mean_elapsed_seconds']}s "
            f"(planej.+exec.={summary['mean_planning_execution_seconds']}s)"
        )
    print(f"\nRelatório: {output_path}")


if __name__ == "__main__":
    main()
