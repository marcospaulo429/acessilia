"""Testes do loader Dr.DocBench com fixtures sinteticas (sem baixar o dataset)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.benchmarks.drdocbench.dataset import (
    Block,
    DrDocBenchDataset,
    PageId,
)

DOC = "a8727f40-f59f-4e0d-be5b-4104252375b2"


def _write_page(root: Path, split: str, subject: str, doc: str, page_no: int, record: list) -> None:
    doc_dir = root / split / subject / doc
    (doc_dir / "images").mkdir(parents=True, exist_ok=True)
    (doc_dir / "images" / f"page_{page_no}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    if split == "dev":
        (doc_dir / "json").mkdir(exist_ok=True)
        (doc_dir / "json" / f"{doc}_page_{page_no}.json").write_text(json.dumps(record))
        (doc_dir / "mds").mkdir(exist_ok=True)
        (doc_dir / "mds" / f"{doc}_{page_no}.md").write_text("**Table 20.1.** Tabulated Results\n")


@pytest.fixture
def dataset_root(tmp_path: Path) -> Path:
    record = [
        {
            "page_info": {
                "page_name": DOC,
                "page_no": 258,
                "height": 744,
                "width": 462,
                "page_attribute": {
                    "data_source": "academic_literature",
                    "subject": "EDUCATION",
                    "challenge_type": "structural_reconstruction",
                    "language": "english",
                    "layout": "other_layout",
                    "special_issue": ["table_horizontal", "table_fewer_line"],
                },
            },
            "layout_dets": [
                {
                    "category_type": "table_caption",
                    "poly": [42.9, 348.2, 54.1, 348.2, 54.1, 673.9, 42.9, 673.9],
                    "ignore": False,
                    "order": 1,
                    "anno_id": 9,
                    "text": "**Table 20.1.** Tabulated Results",
                    "attribute": {"text_rotate": "rotate270"},
                },
                {
                    "category_type": "table",
                    "poly": [56.4, 49.0, 380.2, 49.0, 380.2, 673.4, 56.4, 673.4],
                    "ignore": False,
                    "order": 2,
                    "anno_id": 2,
                    "latex": "\\begin{tabular}{ll} a & b \\end{tabular}",
                    "html": "<table><tr><td>a</td><td>b</td></tr></table>",
                    "attribute": {"with_span": "false"},
                },
                {
                    "category_type": "text_block",
                    "poly": [0, 0, 1, 0, 1, 1, 0, 1],
                    "ignore": False,
                    "order": 4,
                    "anno_id": 4,
                    "text": "Body text.",
                },
                {
                    "category_type": "table_footnote",
                    "poly": [0, 0, 1, 0, 1, 1, 0, 1],
                    "ignore": False,
                    "order": 3,
                    "anno_id": 7,
                    "text": "Note: footnote.",
                },
                {
                    "category_type": "page_number",
                    "poly": [0, 0, 1, 0, 1, 1, 0, 1],
                    "ignore": False,
                    "anno_id": 12,
                    "text": "258",
                },
            ],
            "extra": {
                "relation": [
                    {"source_anno_id": 2, "target_anno_id": 7, "relation_type": "parent_son"},
                    {"source_anno_id": 2, "target_anno_id": 9, "relation_type": "parent_son"},
                ]
            },
        }
    ]
    _write_page(tmp_path, "dev", "EDUCATION", DOC, 258, record)
    _write_page(tmp_path, "dev", "EDUCATION", DOC, 259, [])  # pagina em branco
    _write_page(tmp_path, "test", "MEDICAL", "deadbeef", 7, [])
    return tmp_path


def test_iterates_dev_pages_with_ground_truth(dataset_root: Path) -> None:
    pages = list(DrDocBenchDataset(dataset_root, "dev"))
    assert [p.page_id for p in pages] == [
        PageId("EDUCATION", DOC, 258),
        PageId("EDUCATION", DOC, 259),
    ]
    page = pages[0]
    assert page.has_ground_truth
    assert (page.width, page.height) == (462, 744)
    assert page.page_attribute["special_issue"] == ["table_horizontal", "table_fewer_line"]
    assert len(page.blocks) == 5
    assert page.relations[0].relation_type == "parent_son"
    assert page.gt_markdown().startswith("**Table 20.1.**")


def test_ordered_blocks_excludes_page_elements_and_sorts_by_order(dataset_root: Path) -> None:
    page = next(iter(DrDocBenchDataset(dataset_root, "dev")))
    ordered = page.ordered_blocks()
    assert [b.category_type for b in ordered] == [
        "table_caption",
        "table",
        "table_footnote",
        "text_block",
    ]
    assert all(b.category_type != "page_number" for b in ordered)


def test_blank_page_is_flagged(dataset_root: Path) -> None:
    pages = list(DrDocBenchDataset(dataset_root, "dev"))
    assert pages[1].blank is True
    assert pages[1].blocks == []


def test_test_split_has_no_ground_truth(dataset_root: Path) -> None:
    ds = DrDocBenchDataset(dataset_root, "test")
    pages = list(ds)
    assert len(pages) == 1
    assert pages[0].page_id == PageId("MEDICAL", "deadbeef", 7)
    assert not pages[0].has_ground_truth
    assert ds.page_ids() == [PageId("MEDICAL", "deadbeef", 7)]


def test_stats_counts(dataset_root: Path) -> None:
    stats = DrDocBenchDataset(dataset_root, "dev").stats()
    assert stats["pages"] == 2
    assert stats["documents"] == 1
    assert stats["blank_pages"] == 1
    assert stats["blocks"] == 5
    assert stats["category_type"]["table"] == 1
    assert stats["special_issue"] == {"table_horizontal": 1, "table_fewer_line": 1}
    assert stats["layout"] == {"other_layout": 1}


def test_missing_split_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        DrDocBenchDataset(tmp_path, "dev")


def test_block_from_json_defaults() -> None:
    block = Block.from_json({"category_type": "figure", "poly": [1, 2, 3, 4, 5, 6, 7, 8], "anno_id": 3})
    assert block.order is None
    assert block.is_page_element  # sem ordem => nao pontuado na leitura
    assert block.attribute == {}
