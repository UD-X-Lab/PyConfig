#!/usr/bin/env python3
"""
Summarize alive URLs per file, categorizing by protocol.

For each provided file (default: pipfile/pyproject/requirements/setup alive lists),
writes category-specific files and a dead_links_stats.json-style summary under
`data/links/summary/<category_name>/`.
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List

DEFAULT_INPUTS = (
    Path("data/links/pipfile/alive_urls.txt"),
    Path("data/links/pyproject/alive_urls.txt"),
    Path("data/links/requirements/alive_urls.txt"),
    Path("data/links/setup/alive_urls.txt"),
)

DEFAULT_BASE_OUTPUT = Path("data/links/summary")

CATEGORY_FILENAMES = {
    "http": "alive_http_urls.txt",
    "https": "alive_https_urls.txt",
    "git": "alive_git_urls.txt",
    "hg": "alive_hg_urls.txt",
    "bzr": "alive_bzr_urls.txt",
    "svn": "alive_svn_urls.txt",
    "rest": "alive_other_urls.txt",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize alive URLs per file.")
    parser.add_argument(
        "--inputs",
        nargs="*",
        type=Path,
        default=list(DEFAULT_INPUTS),
        help="List of alive URLs files to process individually.",
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=DEFAULT_BASE_OUTPUT,
        help="Base output directory.",
    )
    return parser.parse_args()


def read_urls(path: Path) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]


def categorize(url: str) -> str:
    lower = url.lower()
    if lower.startswith("http://"):
        return "http"
    if lower.startswith("https://"):
        return "https"
    if lower.startswith(("git://", "git+", "ssh://")):
        return "git"
    if lower.startswith(("hg://", "hg+")):
        return "hg"
    if lower.startswith(("bzr://", "bzr+")):
        return "bzr"
    if lower.startswith(("svn://", "svn+")):
        return "svn"
    return "rest"


def dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    ordered: Dict[str, None] = OrderedDict()
    for item in items:
        ordered.setdefault(item, None)
    return list(ordered.keys())


def summarize_file(input_path: Path, output_dir: Path) -> None:
    urls = read_urls(input_path)
    categories: Dict[str, List[str]] = {key: [] for key in CATEGORY_FILENAMES.keys()}

    for url in urls:
        category = categorize(url)
        categories[category].append(url)

    for key in categories.keys():
        categories[key] = dedupe_preserve_order(categories[key])

    output_dir.mkdir(parents=True, exist_ok=True)

    for category, filename in CATEGORY_FILENAMES.items():
        with (output_dir / filename).open("w", encoding="utf-8") as fh:
            for url in categories[category]:
                fh.write(url)
                fh.write("\n")

    stats = {category: len(categories[category]) for category in CATEGORY_FILENAMES.keys()}
    stats["total"] = sum(stats.values())
    (output_dir / "alive_links_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    for input_path in args.inputs:
        parent_name = input_path.parent.name
        output_dir = args.output_base / parent_name / "alive"
        summarize_file(input_path, output_dir)


if __name__ == "__main__":
    main()
