from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any


def verify_pdf(path: Path, paper: dict[str, Any]) -> None:
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"{paper['id']}: resposta não é PDF")
    if len(data) != paper["size_bytes"]:
        raise ValueError(
            f"{paper['id']}: tamanho {len(data)} != {paper['size_bytes']}"
        )
    digest = hashlib.sha256(data).hexdigest()
    if digest != paper["sha256"]:
        raise ValueError(
            f"{paper['id']}: SHA-256 {digest} != {paper['sha256']}"
        )


def download_corpus(manifest_path: Path, output_dir: Path) -> list[Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    papers = manifest.get("papers")
    if not isinstance(papers, list) or not papers:
        raise ValueError("manifesto sem papers")

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for paper in papers:
        if not isinstance(paper, dict):
            raise ValueError("entrada de paper inválida")
        destination = output_dir / f"{paper['id']}.pdf"
        if destination.exists():
            verify_pdf(destination, paper)
        else:
            temporary = destination.with_suffix(".pdf.part")
            request = urllib.request.Request(
                paper["url"],
                headers={"User-Agent": "acessilia-scientific-benchmark/1.0"},
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    temporary.write_bytes(response.read())
                verify_pdf(temporary, paper)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        downloaded.append(destination)
        print(f"OK {paper['id']} {paper['sha256']}")
    return downloaded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baixa e verifica o corpus científico fixado."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/scientific_papers/corpus.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("var/data/scientific-benchmark"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        download_corpus(args.manifest.resolve(), args.output_dir.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())