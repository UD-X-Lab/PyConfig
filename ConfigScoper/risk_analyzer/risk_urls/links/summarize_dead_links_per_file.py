#!/usr/bin/env python3
"""
Produce per-file statistics for dead URLs grouped by protocol categories.

For each provided dead_urls.txt file, this script creates a subdirectory under
`data/links/summary/` (or a user-specified directory) named after the parent
folder of the input (e.g., pipfile, pyproject) and writes:

    * One text file per category (http, https, git, hg, bzr, svn, rest)
    * A JSON file summarizing the counts per category for that input
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List

DEFAULT_INPUTS = (
    Path("data/links/pipfile/dead_urls.txt"),
    Path("data/links/pyproject/dead_urls.txt"),
    Path("data/links/requirements/dead_urls.txt"),
    Path("data/links/setup/dead_urls.txt"),
)

DEFAULT_BASE_OUTPUT = Path("data/links/summary")

CATEGORY_FILENAMES = {
    "http": "dead_http_urls.txt",
    "https": "dead_https_urls.txt",
    "git": "dead_git_urls.txt",
    "hg": "dead_hg_urls.txt",
    "bzr": "dead_bzr_urls.txt",
    "svn": "dead_svn_urls.txt",
    "rest": "dead_other_urls.txt",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize dead URLs per file.")
    parser.add_argument(
        "--inputs",
        nargs="*",
        type=Path,
        default=list(DEFAULT_INPUTS),
        help="List of dead_urls.txt files to process individually.",
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=DEFAULT_BASE_OUTPUT,
        help="Base directory for per-file summaries.",
    )
    return parser.parse_args()


def read_links(path: Path) -> List[str]:
    links: List[str] = []
    if not path.exists():
        return links
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if line and not line.startswith("#"):
                links.append(line)
    return links


def categorize(link: str) -> str:
    lower = link.lower()
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
    links = read_links(input_path)
    categories: Dict[str, List[str]] = {key: [] for key in CATEGORY_FILENAMES}

    for link in links:
        category = categorize(link)
        categories[category].append(link)

    # Deduplicate while preserving order
    for key in categories:
        categories[key] = dedupe_preserve_order(categories[key])

    output_dir.mkdir(parents=True, exist_ok=True)
    for category, filename in CATEGORY_FILENAMES.items():
        target = output_dir / filename
        with target.open("w", encoding="utf-8") as fh:
            for link in categories[category]:
                fh.write(link)
                fh.write("\n")

    stats = {category: len(categories[category]) for category in CATEGORY_FILENAMES}
    stats["total"] = sum(stats.values())
    stats_path = output_dir / "dead_links_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()

    for input_path in args.inputs:
        parent_name = input_path.parent.name or input_path.stem
        output_dir = args.output_base / parent_name
        summarize_file(input_path, output_dir)


if __name__ == "__main__":
    main()
