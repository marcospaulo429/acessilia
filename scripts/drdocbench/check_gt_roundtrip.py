"""Teste de ouro: GT JSON -> canonico -> Markdown deve reproduzir os mds/ oficiais.

Roda sobre o dataset baixado; imprime paginas com menor similaridade para inspecao.
Uso: python scripts/drdocbench/check_gt_roundtrip.py [--root var/data/drdocbench] [--limit N]
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.benchmarks.drdocbench.dataset import DrDocBenchDataset  # noqa: E402
from backend.benchmarks.drdocbench.gt_adapter import page_to_canonical_document  # noqa: E402
from backend.export.renderers.drdocbench_markdown import (  # noqa: E402
    MASK_CATEGORIES,
    render_drdocbench_markdown,
)

_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_STYLE = re.compile(r'\s+style="[^"]*"')
_INLINE_MATH_SPAN = re.compile(r'<span\s+class="math inline">(.*?)</span>', re.S)
_WS = re.compile(r"\s+")


def normalize(md: str) -> str:
    md = _IMG.sub("", md)
    md = _STYLE.sub("", md)
    md = _INLINE_MATH_SPAN.sub(r"\1", md)
    md = md.replace("$$", "").replace("\\[", "").replace("\\]", "")
    return _WS.sub(" ", md).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("var/data/drdocbench"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--show", type=int, default=5, help="piores paginas a exibir")
    args = parser.parse_args(argv)

    scores: list[tuple[float, str]] = []
    for i, page in enumerate(DrDocBenchDataset(args.root, "dev")):
        if args.limit and i >= args.limit:
            break
        if page.blank or page.gt_md_path is None:
            continue
        # mds/ oficiais incluem header/footer/page_number; mantemos para comparar 1:1.
        ours = normalize(
            render_drdocbench_markdown(
                page_to_canonical_document(page, include_page_elements=True),
                formula_style="dollars",
                skip_categories=MASK_CATEGORIES,
            )
        )
        ref = normalize(page.gt_markdown() or "")
        ratio = difflib.SequenceMatcher(None, ours, ref, autojunk=False).ratio() if (ours or ref) else 1.0
        scores.append((ratio, page.page_id.key))

    if not scores:
        print("nenhuma pagina com GT encontrada")
        return 1
    scores.sort()
    mean = sum(s for s, _ in scores) / len(scores)
    perfect = sum(1 for s, _ in scores if s >= 0.999)
    print(f"paginas: {len(scores)}  media: {mean:.4f}  >=0.999: {perfect}  <0.95: {sum(1 for s,_ in scores if s < 0.95)}")
    for ratio, key in scores[: args.show]:
        print(f"  {ratio:.4f}  {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
