"""Testes do renderer Markdown do desafio Dr.DocBench."""

from __future__ import annotations

from backend.benchmarks.drdocbench.dataset import Block
from backend.benchmarks.drdocbench.gt_adapter import block_to_canonical
from backend.export.renderers.drdocbench_markdown import (
    render_blocks,
    render_drdocbench_markdown,
)


def test_heading_paragraph_and_list() -> None:
    blocks = [
        {"type": "heading", "title": "Conversion Tables", "level": 1},
        {"type": "paragraph", "text": "American measurements\n\n\n\nare used."},
        {"type": "list", "ordered": False, "items": ["a", "b"]},
        {"type": "list", "ordered": True, "items": ["x", "y"]},
    ]
    md = render_blocks(blocks)
    assert md == "# Conversion Tables\n\nAmerican measurements\n\nare used.\n\n- a\n- b\n\n1. x\n2. y\n"


def test_math_display_brackets_and_dollars() -> None:
    block = {"type": "math", "text": "$$\nE = mc^2\n$$"}
    assert render_blocks([block]) == "\\[\nE = mc^2\n\\]\n"
    assert render_blocks([block], formula_style="dollars") == "$$\nE = mc^2\n$$\n"
    assert render_blocks([{"type": "math", "text": "\\[ a+b \\]"}]) == "\\[\na+b\n\\]\n"


def test_code_block_with_language() -> None:
    md = render_blocks([{"type": "code", "language": "python", "text": "print(1)\n"}])
    assert md == "```python\nprint(1)\n```\n"


def test_table_from_ast_keeps_empty_cells_and_spans() -> None:
    block = {
        "type": "table",
        "table_ast": {
            "header": [{"cells": [{"text": "A", "header": True, "colspan": 2}]}],
            "body": [
                {"cells": [{"text": "1"}, {"text": ""}]},
                {"cells": [{"text": "2", "rowspan": 2}, {"text": "x & y"}]},
            ],
        },
    }
    md = render_blocks([block])
    assert md.startswith("<table>\n<thead>\n<tr>\n<th colspan=\"2\">A</th>\n</tr>\n</thead>\n<tbody>")
    assert "<td>1</td>\n<td></td>" in md
    assert '<td rowspan="2">2</td>' in md
    assert "x &amp; y" in md
    assert md.rstrip().endswith("</table>")


def test_table_prefers_prerendered_html() -> None:
    html = "<table><tr><td>a</td></tr></table>"
    assert render_blocks([{"type": "table", "metadata": {"html": html}}]) == html + "\n"


def test_page_elements_and_figures_are_skipped() -> None:
    blocks = [
        {"type": "paragraph", "text": "Header", "metadata": {"category": "header"}},
        {"type": "paragraph", "text": "12", "metadata": {"category": "page_number"}},
        {"type": "image", "alt_text": "foto", "metadata": {"category": "figure"}},
        {"type": "paragraph", "text": "Legenda", "metadata": {"category": "figure_caption"}},
    ]
    assert render_blocks(blocks) == "Legenda\n"


def test_image_text_only_when_transcribed() -> None:
    assert render_blocks([{"type": "image", "text": "eixo x"}]) == ""
    assert render_blocks([{"type": "image", "text": "eixo x", "metadata": {"transcribed": True}}]) == "eixo x\n"


def test_document_sections_and_synthetic_root() -> None:
    doc = {
        "sections": [
            {
                "title": "",
                "metadata": {"synthetic": True},
                "blocks": [{"type": "paragraph", "text": "intro"}],
                "children": [
                    {"title": "Sub", "level": 2, "blocks": [{"type": "paragraph", "text": "corpo"}]}
                ],
            }
        ]
    }
    assert render_drdocbench_markdown(doc) == "intro\n\n## Sub\n\ncorpo\n"


def test_gt_adapter_maps_categories() -> None:
    table = Block.from_json(
        {
            "anno_id": 2,
            "category_type": "table",
            "poly": [],
            "order": 1,
            "html": '<table>\n<tr>\n<td style="text-align: left;">a</td>\n</tr>\n</table>',
        }
    )
    eq = Block.from_json(
        {"anno_id": 3, "category_type": "equation_isolated", "poly": [], "order": 2, "latex": "$$\nx^2\n$$"}
    )
    code = Block.from_json(
        {"anno_id": 4, "category_type": "code_algorithm", "poly": [], "order": 3, "text": "```python\nprint(1)\n```"}
    )
    title = Block.from_json({"anno_id": 5, "category_type": "title", "poly": [], "order": 4, "text": "T\n\n\n\n"})
    md = render_blocks([block_to_canonical(b) for b in (table, eq, code, title)])
    assert md == (
        "<table>\n<tr>\n<td>a</td>\n</tr>\n</table>\n\n"
        "\\[\nx^2\n\\]\n\n"
        "```python\nprint(1)\n```\n\n"
        "# T\n"
    )
