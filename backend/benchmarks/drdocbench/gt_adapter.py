"""Converte blocos de ground truth Dr.DocBench (OmniDocJSON) em blocos canonicos.

Serve a dois propositos:
* teste de ouro do renderer Markdown (GT -> canonico -> Markdown ~= ``mds/``);
* semente do ``WorldState`` em experimentos *oracle* (melhor provedor por bloco).
"""

from __future__ import annotations

import re
from typing import Any

from backend.benchmarks.drdocbench.dataset import Block, Page

CATEGORY_TO_TYPE: dict[str, str] = {
    "title": "heading",
    "text_block": "paragraph",
    "figure_caption": "paragraph",
    "figure_footnote": "paragraph",
    "table_caption": "paragraph",
    "table_footnote": "paragraph",
    "page_footnote": "paragraph",
    "reference": "paragraph",
    "code_txt": "paragraph",
    "code_algorithm": "code",
    "table": "table",
    "equation_isolated": "math",
    "figure": "image",
    "header": "paragraph",
    "footer": "paragraph",
    "page_number": "paragraph",
    "text_mask": "paragraph",
    "table_mask": "paragraph",
}

_STYLE_ATTR = re.compile(r'\s+style="[^"]*"')
_CODE_FENCE = re.compile(r"^```[\w+-]*\n?|\n?```\s*$")


def block_to_canonical(block: Block) -> dict[str, Any]:
    block_type = CATEGORY_TO_TYPE.get(block.category_type, "paragraph")
    canonical: dict[str, Any] = {
        "id": f"gt-{block.anno_id}",
        "type": block_type,
        "metadata": {
            "category": block.category_type,
            "anno_id": block.anno_id,
            "order": block.order,
            "poly": block.poly,
            "attribute": block.attribute,
        },
    }
    text = block.text or ""
    if block_type == "heading":
        canonical["title"] = text.strip()
        canonical["level"] = 1
    elif block_type == "math":
        canonical["text"] = (block.latex or text).strip()
    elif block_type == "table":
        canonical["text"] = ""
        canonical["metadata"]["html"] = _STYLE_ATTR.sub("", block.html or "").strip()
        if block.latex:
            canonical["metadata"]["latex"] = block.latex
    elif block_type == "code":
        canonical["text"] = _CODE_FENCE.sub("", text).rstrip("\n")
        m = re.match(r"^```([\w+-]+)", text)
        canonical["language"] = m.group(1) if m else ""
    else:
        canonical["text"] = text
    return canonical


def page_to_canonical_blocks(page: Page, *, include_page_elements: bool = False) -> list[dict[str, Any]]:
    """Blocos canonicos na ordem de leitura do GT.

    Page elements (header/footer/page_number) nao tem ``order``; quando incluidos,
    vao ao final na ordem em que aparecem no JSON.
    """
    blocks = [block_to_canonical(b) for b in page.ordered_blocks()]
    if include_page_elements:
        blocks.extend(block_to_canonical(b) for b in page.blocks if b.is_page_element and not b.ignore)
    return blocks


def page_to_canonical_document(page: Page, *, include_page_elements: bool = False) -> dict[str, Any]:
    return {
        "metadata": {
            "source": "drdocbench-gt",
            "subject": page.page_id.subject,
            "document_id": page.page_id.document_id,
            "page": page.page_id.page,
        },
        "sections": [
            {
                "title": "",
                "level": 1,
                "metadata": {"synthetic": True},
                "blocks": page_to_canonical_blocks(page, include_page_elements=include_page_elements),
                "children": [],
            }
        ],
    }
