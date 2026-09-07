"""Avaliação local no split ``dev`` com o avaliador oficial (DrDocBench/OmniDocBench).

Fluxo:
1. converte ``predictions.jsonl`` (formato EvalAI) para o layout esperado pelo
   avaliador multipágina com janela de 1 página:
   ``pred_root/{subject}/{doc_id}_page_{N}-{N}.md``;
2. gera um config YAML single-page (CDM opcional — exige TeXLive/ImageMagick);
3. executa ``tools/multipage_pdf_validation.py`` no venv 3.10
   (``third_party/.venv-eval``) com cwd em ``third_party/DrDocBench``;
4. le ``result/<name>_metric_result.json`` e imprime/salva um resumo no estilo
   do desafio (componentes em 0–100 e media), alem dos recortes por atributo.

Uso:
    python scripts/drdocbench/evaluate.py --pred predictions.jsonl --name docling-v1
    python scripts/drdocbench/evaluate.py --from-gt --name gt-roundtrip   # calibracao (~100)
    python scripts/drdocbench/evaluate.py --from-gt-md --name gt-mds      # mds/ oficiais
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.benchmarks.drdocbench.dataset import DrDocBenchDataset, PageId  # noqa: E402
from backend.benchmarks.drdocbench.gt_adapter import page_to_canonical_document  # noqa: E402
from backend.benchmarks.drdocbench.submission import prediction_record, read_jsonl  # noqa: E402
from backend.export.renderers.drdocbench_markdown import render_drdocbench_markdown  # noqa: E402

EVAL_REPO = ROOT / "third_party" / "DrDocBench"
EVAL_PYTHON = ROOT / "third_party" / ".venv-eval" / "bin" / "python"
REPORTS = ROOT / "var" / "reports" / "eval"

# Mapeia elementos do avaliador -> componente do desafio e direcao da metrica.
COMPONENTS = {
    "text_block": ("Text", "Edit_dist", "lower"),
    "display_formula": ("Formula", "CDM", "higher"),
    "table": ("Table", "TEDS", "higher"),
    "reading_order": ("ReadingOrder", "Edit_dist", "lower"),
}


def build_config(with_cdm: bool, exclude_subjects: list[str]) -> dict[str, Any]:
    formula_metrics = ["Edit_dist"] + (["CDM"] if with_cdm else [])
    return {
        "end2end_eval": {
            "metrics": {
                "text_block": {"metric": ["Edit_dist"]},
                "display_formula": {"metric": formula_metrics},
                "table": {"metric": ["TEDS", "Edit_dist"]},
                "reading_order": {"metric": ["Edit_dist"]},
            },
            "dataset": {
                "dataset_name": "multipage_end2end_dataset",
                "ground_truth": {"data_path": ""},
                "prediction": {"data_path": ""},
                "match_method": "quick_match",
                "exclude_subjects": exclude_subjects,
            },
        }
    }


def write_pred_tree(records: list[dict[str, Any]], pred_root: Path) -> int:
    n = 0
    for rec in records:
        subject = str(rec["subject"])
        doc = str(rec["document_id"])
        page = int(rec["page"])
        out = pred_root / subject / f"{doc}_page_{page}-{page}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(rec.get("markdown") or ""), encoding="utf-8")
        n += 1
    return n


def records_from_gt(root: Path, *, use_official_md: bool, limit: int = 0) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for i, page in enumerate(DrDocBenchDataset(root, "dev")):
        if limit and i >= limit:
            break
        if page.blank:
            continue
        if use_official_md:
            md = page.gt_markdown() or ""
        else:
            md = render_drdocbench_markdown(page_to_canonical_document(page))
        records.append(prediction_record(page.page_id, md))
    return records


def run_evaluator(config_path: Path, gt_root: Path, pred_root: Path, name: str) -> Path:
    if not EVAL_PYTHON.exists():
        raise SystemExit(
            f"venv de avaliacao ausente em {EVAL_PYTHON}. Crie com: "
            "uv venv --python 3.10 third_party/.venv-eval && "
            "uv pip install --python third_party/.venv-eval/bin/python -e third_party/OmniDocBench"
        )
    cmd = [
        str(EVAL_PYTHON),
        "tools/multipage_pdf_validation.py",
        "--config", str(config_path),
        "--gt_root", str(gt_root),
        "--pred_path", str(pred_root),
        "--save_name", name,
    ]
    env = {**os.environ, "PYTHONPATH": str(EVAL_REPO)}
    (EVAL_REPO / "result").mkdir(exist_ok=True)  # o avaliador nao cria a pasta antes de gravar
    subprocess.run(cmd, cwd=EVAL_REPO, env=env, check=True)
    return EVAL_REPO / "result" / f"{name}_metric_result.json"


def _to_score(value: float, direction: str, scale_100: bool) -> float:
    v = float(value)
    if direction == "lower":
        return (1.0 - v) * 100.0
    return v * 100.0 if not scale_100 and v <= 1.0 else v


def _extract(metric_block: Any) -> float | None:
    """Valor escalar de um bloco de metrica do avaliador (``ALL_page_avg`` preferido)."""
    if isinstance(metric_block, dict):
        for key in ("ALL_page_avg", "ALL", "all", "edit_sample_avg", "edit_whole"):
            if key in metric_block:
                metric_block = metric_block[key]
                break
        else:
            return None
    if metric_block is None or isinstance(metric_block, (dict, list)):
        return None
    try:
        v = float(metric_block)
    except (TypeError, ValueError):
        return None
    return None if v != v else v  # NaN -> ausente


def summarize(metric_result: dict[str, Any]) -> dict[str, Any]:
    """Resumo no estilo do desafio a partir do agregado do avaliador.

    Nota: a media aqui e sobre componentes agregados (nao por pagina); a
    formula oficial faz a media por pagina pontuavel. Serve para comparar
    configuracoes entre si; o numero oficial vem do EvalAI.
    """
    components: dict[str, float] = {}
    raw: dict[str, Any] = {}
    for element, (label, metric, direction) in COMPONENTS.items():
        all_scores = (metric_result.get(element) or {}).get("all") or {}
        value = _extract(all_scores.get(metric))
        if value is None and metric == "CDM":
            value = _extract(all_scores.get("Edit_dist"))
            metric, direction = "Edit_dist(proxy CDM)", "lower"
        if value is None:
            continue
        raw[label] = {metric: value}
        components[label] = round(_to_score(value, direction, scale_100=(metric == "CDM")), 2)
    overall = round(sum(components.values()) / len(components), 2) if components else None
    return {"components": components, "overall_mean_of_components": overall, "raw": raw}


def per_attribute(metric_result: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for element in COMPONENTS:
        block = metric_result.get(element) or {}
        out[element] = {"group": block.get("group") or {}, "page": block.get("page") or {}}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--pred", type=Path, help="predictions.jsonl (formato EvalAI)")
    src.add_argument("--from-gt", action="store_true", help="GT -> canonico -> nosso renderer")
    src.add_argument("--from-gt-md", action="store_true", help="usa os mds/ oficiais como predicao")
    parser.add_argument("--root", type=Path, default=ROOT / "var" / "data" / "drdocbench")
    parser.add_argument("--name", required=True, help="nome da execucao (prefixo dos resultados)")
    parser.add_argument("--limit", type=int, default=0, help="limita paginas (modos --from-gt*)")
    parser.add_argument("--cdm", action="store_true", help="habilita CDM (exige TeXLive/ImageMagick)")
    parser.add_argument("--exclude-subjects", default="MUSIC", help="lista separada por virgula")
    args = parser.parse_args(argv)

    run_dir = REPORTS / args.name
    pred_root = run_dir / "pred"
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.pred:
        records = read_jsonl(args.pred)
    else:
        records = records_from_gt(args.root, use_official_md=args.from_gt_md, limit=args.limit)
    n = write_pred_tree(records, pred_root)
    print(f"predicoes escritas: {n} -> {pred_root}")

    config_path = run_dir / "config.yaml"
    excluded = [s for s in args.exclude_subjects.split(",") if s]
    config_path.write_text(yaml.safe_dump(build_config(args.cdm, excluded), sort_keys=False))

    result_path = run_evaluator(config_path, args.root / "dev", pred_root, args.name)
    metric_result = json.loads(result_path.read_text(encoding="utf-8"))

    summary = {
        "name": args.name,
        "pages_predicted": n,
        **summarize(metric_result),
        "by_attribute": per_attribute(metric_result),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({k: summary[k] for k in ("components", "overall_mean_of_components")}, indent=2))
    print(f"resumo: {run_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
