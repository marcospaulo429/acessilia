"""Loader do dataset Dr.DocBench (formato OmniDocJSON, uma pagina por registro).

Layout em disco (HF ``2077AIDataFoundation/DrDocBench``)::

    dev/<SUBJECT>/<document_uuid>/images/page_<N>.jpg
    dev/<SUBJECT>/<document_uuid>/json/<document_uuid>_page_<N>.json   (GT)
    dev/<SUBJECT>/<document_uuid>/mds/<document_uuid>_<N>.md            (GT em Markdown)
    test/<SUBJECT>/<document_uuid>/images/page_<N>.jpg                  (sem GT)

Identificador de uma pagina para submissao: ``(subject, document_id, page)``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Categorias de bloco que NAO entram na ordem de leitura nem no texto pontuado.
PAGE_ELEMENT_CATEGORIES = frozenset({"header", "footer", "page_number", "page_footnote", "aside_text"})

_PAGE_RE = re.compile(r"page_(\d+)\.jpg$")


@dataclass(frozen=True)
class PageId:
    subject: str
    document_id: str
    page: int

    @property
    def key(self) -> str:
        return f"{self.subject}/{self.document_id}/{self.page}"


@dataclass
class Block:
    anno_id: int
    category_type: str
    poly: list[float]
    order: int | None
    ignore: bool
    text: str | None = None
    latex: str | None = None
    html: str | None = None
    attribute: dict[str, Any] = field(default_factory=dict)

    @property
    def is_page_element(self) -> bool:
        return self.order is None or self.category_type in PAGE_ELEMENT_CATEGORIES

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "Block":
        return cls(
            anno_id=int(raw.get("anno_id", -1)),
            category_type=str(raw.get("category_type", "unknown")),
            poly=[float(v) for v in raw.get("poly", [])],
            order=raw.get("order"),
            ignore=bool(raw.get("ignore", False)),
            text=raw.get("text"),
            latex=raw.get("latex"),
            html=raw.get("html"),
            attribute=dict(raw.get("attribute") or {}),
        )


@dataclass
class Relation:
    source_anno_id: int
    target_anno_id: int
    relation_type: str


@dataclass
class Page:
    page_id: PageId
    image_path: Path
    gt_json_path: Path | None = None
    gt_md_path: Path | None = None
    width: int | None = None
    height: int | None = None
    page_attribute: dict[str, Any] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    blank: bool = False

    @property
    def has_ground_truth(self) -> bool:
        return self.gt_json_path is not None

    def ordered_blocks(self) -> list[Block]:
        """Blocos pontuados na ordem de leitura (exclui page elements e ``ignore``)."""
        scored = [b for b in self.blocks if not b.ignore and not b.is_page_element]
        return sorted(scored, key=lambda b: b.order if b.order is not None else 10**9)

    def gt_markdown(self) -> str | None:
        if self.gt_md_path and self.gt_md_path.exists():
            return self.gt_md_path.read_text(encoding="utf-8")
        return None


def _load_gt(page: Page) -> None:
    assert page.gt_json_path is not None
    raw = json.loads(page.gt_json_path.read_text(encoding="utf-8"))
    if not raw:
        page.blank = True
        return
    record = raw[0] if isinstance(raw, list) else raw
    info = record.get("page_info", {})
    page.width = info.get("width")
    page.height = info.get("height")
    page.page_attribute = dict(info.get("page_attribute") or {})
    page.blocks = [Block.from_json(b) for b in record.get("layout_dets", [])]
    page.relations = [
        Relation(int(r["source_anno_id"]), int(r["target_anno_id"]), str(r["relation_type"]))
        for r in (record.get("extra") or {}).get("relation", [])
    ]


class DrDocBenchDataset:
    """Itera paginas de um split (``dev`` ou ``test``)."""

    def __init__(self, root: Path | str, split: str = "dev", load_gt: bool = True) -> None:
        self.root = Path(root)
        self.split = split
        self.load_gt = load_gt
        self.split_dir = self.root / split
        if not self.split_dir.is_dir():
            raise FileNotFoundError(f"split '{split}' nao encontrado em {self.root}")

    def __iter__(self) -> Iterator[Page]:
        for image_path in sorted(self.split_dir.glob("*/*/images/page_*.jpg")):
            yield self._page_from_image(image_path)

    def __len__(self) -> int:
        return sum(1 for _ in self.split_dir.glob("*/*/images/page_*.jpg"))

    def _page_from_image(self, image_path: Path) -> Page:
        doc_dir = image_path.parent.parent
        subject = doc_dir.parent.name
        document_id = doc_dir.name
        m = _PAGE_RE.search(image_path.name)
        if not m:
            raise ValueError(f"nome de imagem inesperado: {image_path}")
        page_no = int(m.group(1))
        page = Page(
            page_id=PageId(subject, document_id, page_no),
            image_path=image_path,
        )
        gt_json = doc_dir / "json" / f"{document_id}_page_{page_no}.json"
        gt_md = doc_dir / "mds" / f"{document_id}_{page_no}.md"
        if gt_json.exists():
            page.gt_json_path = gt_json
        if gt_md.exists():
            page.gt_md_path = gt_md
        if self.load_gt and page.gt_json_path is not None:
            _load_gt(page)
        return page

    def page_ids(self) -> list[PageId]:
        return [p.page_id for p in DrDocBenchDataset(self.root, self.split, load_gt=False)]

    def stats(self) -> dict[str, Any]:
        """Contagens uteis para reproduzir o card do dataset e priorizar provedores."""
        pages = list(self)
        counts: dict[str, Counter[str]] = {
            "category_type": Counter(),
            "special_issue": Counter(),
            "layout": Counter(),
            "data_source": Counter(),
            "challenge_type": Counter(),
            "subject": Counter(),
        }
        blank = 0
        documents: set[str] = set()
        for p in pages:
            documents.add(p.page_id.document_id)
            counts["subject"][p.page_id.subject] += 1
            if p.blank:
                blank += 1
                continue
            for b in p.blocks:
                counts["category_type"][b.category_type] += 1
            for key in ("layout", "data_source", "challenge_type"):
                if key in p.page_attribute:
                    counts[key][str(p.page_attribute[key])] += 1
            for issue in p.page_attribute.get("special_issue") or []:
                counts["special_issue"][str(issue)] += 1
        return {
            "split": self.split,
            "pages": len(pages),
            "documents": len(documents),
            "subjects": len(counts["subject"]),
            "blank_pages": blank,
            "blocks": sum(counts["category_type"].values()),
            **{k: dict(v.most_common()) for k, v in counts.items()},
        }
