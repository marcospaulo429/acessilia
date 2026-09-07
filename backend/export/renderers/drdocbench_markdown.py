"""Renderer do documento canonico para o Markdown do desafio Dr.DocBench.

Convencoes (prompt unificado do benchmark + Markdown de referencia do split dev):

* titulos ``# ...``; texto em Markdown puro, no idioma original;
* formulas display em LaTeX (``\\[ ... \\]`` por padrao, ou ``$$ ... $$``);
* tabelas em HTML ``<table>`` com ``rowspan``/``colspan``; celulas vazias preservadas;
* codigo em bloco cercado com tag de linguagem;
* figuras omitidas (o visual nao e pontuado); legendas/rodapes de figura ficam como texto;
* cabecalho, rodape e numero de pagina omitidos (excluidos da avaliacao).
"""

from __future__ import annotations

import re
from html import escape
from typing import Any, Literal

from backend.pipeline.table_ast import table_ast_from_block

FormulaStyle = Literal["brackets", "dollars"]

# Elementos de pagina excluidos da avaliacao (nao entram na ordem de leitura nem no texto).
PAGE_ELEMENT_CATEGORIES = frozenset({"header", "footer", "page_number"})
# Regioes sem conteudo textual pontuavel.
MASK_CATEGORIES = frozenset({"text_mask", "table_mask", "figure", "abandon"})
SKIPPED_CATEGORIES = PAGE_ELEMENT_CATEGORIES | MASK_CATEGORIES

_DISPLAY_DELIMS = re.compile(r"^\s*(?:\$\$|\\\[)\s*|\s*(?:\$\$|\\\])\s*$")


def render_drdocbench_markdown(
    document: dict[str, Any],
    *,
    formula_style: FormulaStyle = "brackets",
    skip_categories: frozenset[str] = SKIPPED_CATEGORIES,
) -> str:
    chunks: list[str] = []
    for section in document.get("sections", []):
        chunks.extend(_render_section(section, formula_style, skip_categories))
    return "\n\n".join(c for c in chunks if c) + ("\n" if chunks else "")


def render_blocks(
    blocks: list[dict[str, Any]],
    *,
    formula_style: FormulaStyle = "brackets",
    skip_categories: frozenset[str] = SKIPPED_CATEGORIES,
) -> str:
    chunks = [_render_block(b, formula_style, skip_categories) for b in blocks]
    return "\n\n".join(c for c in chunks if c) + ("\n" if any(chunks) else "")


def _render_section(
    section: dict[str, Any], formula_style: FormulaStyle, skip_categories: frozenset[str]
) -> list[str]:
    chunks: list[str] = []
    title = (section.get("title") or "").strip()
    if title and not section.get("metadata", {}).get("synthetic"):
        level = int(section.get("level") or 1)
        chunks.append(f"{'#' * max(1, min(level, 6))} {title}")
    for block in section.get("blocks", []):
        chunks.append(_render_block(block, formula_style, skip_categories))
    for child in section.get("children", []):
        chunks.extend(_render_section(child, formula_style, skip_categories))
    return chunks


def _render_block(
    block: dict[str, Any], formula_style: FormulaStyle, skip_categories: frozenset[str]
) -> str:
    metadata = block.get("metadata") or {}
    if metadata.get("category") in skip_categories:
        return ""

    block_type = block.get("type")
    text = _clean(block.get("text", ""))

    if block_type == "heading":
        title = _clean(block.get("title") or text)
        if not title:
            return ""
        level = int(block.get("level") or 1)
        return f"{'#' * max(1, min(level, 6))} {title}"

    if block_type == "list":
        items = [_clean(str(i)) for i in block.get("items", [])]
        items = [i for i in items if i]
        if block.get("ordered"):
            return "\n".join(f"{n}. {item}" for n, item in enumerate(items, start=1))
        return "\n".join(f"- {item}" for item in items)

    if block_type == "code":
        language = (block.get("language") or "").strip()
        raw = block.get("text", "").rstrip("\n")
        return f"```{language}\n{raw}\n```"

    if block_type == "table":
        return _render_table(block)

    if block_type == "image":
        # Visual nao pontuado; texto embutido (rotulos/eixos) pode vir em `text`.
        return text if metadata.get("transcribed") and text else ""

    if block_type == "math":
        return _render_math(block.get("text", ""), formula_style)

    return text


def _render_math(latex: str, formula_style: FormulaStyle) -> str:
    body = _DISPLAY_DELIMS.sub("", latex or "").strip()
    if not body:
        return ""
    if formula_style == "dollars":
        return f"$$\n{body}\n$$"
    return f"\\[\n{body}\n\\]"


def _render_table(block: dict[str, Any]) -> str:
    metadata = block.get("metadata") or {}
    html = metadata.get("html")
    if isinstance(html, str) and "<table" in html:
        return html.strip()

    # table_ast bruto preserva celulas vazias (a grade importa para o TEDS);
    # o normalizador compartilhado as descarta, entao so entra como fallback.
    ast = block.get("table_ast") if isinstance(block.get("table_ast"), dict) else None
    if not ast:
        ast = table_ast_from_block(block)
    if not ast:
        return ""
    header_rows = ast.get("header") or []
    body_rows = (ast.get("body") or []) + (ast.get("footer") or [])
    parts = ["<table>"]
    if header_rows:
        parts.append("<thead>")
        parts.extend(_html_row(r, header=True) for r in header_rows)
        parts.append("</thead>")
    if body_rows:
        parts.append("<tbody>")
        parts.extend(_html_row(r, header=False) for r in body_rows)
        parts.append("</tbody>")
    parts.append("</table>")
    return "\n".join(parts)


def _html_row(row: dict[str, Any], *, header: bool) -> str:
    tag = "th" if header else "td"
    cells: list[str] = []
    for cell in row.get("cells", []) if isinstance(row, dict) else []:
        if not isinstance(cell, dict):
            continue
        attrs = ""
        rowspan = cell.get("rowspan")
        if isinstance(rowspan, int) and rowspan > 1:
            attrs += f' rowspan="{rowspan}"'
        colspan = cell.get("colspan")
        if isinstance(colspan, int) and colspan > 1:
            attrs += f' colspan="{colspan}"'
        cell_tag = "th" if header or cell.get("header") else tag
        cells.append(f"<{cell_tag}{attrs}>{escape(_clean(str(cell.get('text', ''))))}</{cell_tag}>")
    return "<tr>\n" + "\n".join(cells) + "\n</tr>" if cells else "<tr></tr>"


def _clean(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (value or "").replace("\r", "")).strip()
