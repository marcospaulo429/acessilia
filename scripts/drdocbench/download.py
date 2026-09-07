"""Baixa o dataset Dr.DocBench (Hugging Face) para ``var/data/drdocbench``.

Uso:
    python scripts/drdocbench/download.py [--dest DIR] [--split dev|test|all]

As imagens das paginas sao de editoras terceiras e NAO devem ser versionadas;
o destino padrao ja esta no .gitignore.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ID = "2077AIDataFoundation/DrDocBench"
DEFAULT_DEST = Path("var/data/drdocbench")


def download(dest: Path, split: str) -> Path:
    from huggingface_hub import snapshot_download

    patterns: list[str] | None
    if split == "all":
        patterns = None
    else:
        patterns = [f"{split}/**", "README.md"]

    path = snapshot_download(
        repo_id=REPO_ID,
        repo_type="dataset",
        local_dir=str(dest),
        allow_patterns=patterns,
    )
    return Path(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all")
    args = parser.parse_args(argv)

    args.dest.mkdir(parents=True, exist_ok=True)
    path = download(args.dest, args.split)

    n_dev = len(list((path / "dev").glob("*/*/images/*.jpg"))) if (path / "dev").exists() else 0
    n_test = len(list((path / "test").glob("*/*/images/*.jpg"))) if (path / "test").exists() else 0
    print(f"dataset em {path}")
    print(f"dev:  {n_dev} paginas")
    print(f"test: {n_test} paginas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
