#!/usr/bin/env python3
"""
Aggregate dead links from multiple files and split them by protocol/category.

Categories collected:
    - http (http://)
    - https (https://)
    - git (git://, git+, ssh://)
    - hg (hg://, hg+)
    - bzr (bzr://, bzr+)
    - svn (svn://, svn+)
    - rest (everything else)

Outputs:
    * A JSON statistics file summarizing counts per category.
    * One text file per category containing the matching links.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

DEFAULT_INPUTS = (
    Path("data/links/pipfile/dead_urls.txt"),
    Path("data/links/pyproject/dead_urls.txt"),
    Path("data/links/requirements/dead_urls.txt"),
    Path("data/links/setup/dead_urls.txt"),
)

DEFAULT_OUTPUT_DIR = Path("data/links/summary")
DEFAULT_STATS_FILE = DEFAULT_OUTPUT_DIR / "dead_links_stats.json"

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
    parser = argparse.ArgumentParser(description="Summarize dead links by protocol.")
    parser.add_argument(
        "--inputs",
        nargs="*",
        type=Path,
        default=list(DEFAULT_INPUTS),
        help="List of dead_urls.txt files to process.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where category files will be written.",
    )
    parser.add_argument(
        "--stats-file",
        type=Path,
        default=DEFAULT_STATS_FILE,
        help="Path to JSON file containing summary statistics.",
    )
    return parser.parse_args()


def read_links(paths: Iterable[Path]) -> List[str]:
    links: List[str] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
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


def write_categories(
    categories: Dict[str, List[str]],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for category, filename in CATEGORY_FILENAMES.items():
        links = categories.get(category, [])
        target = output_dir / filename
        with target.open("w", encoding="utf-8") as fh:
            for link in links:
                fh.write(link)
                fh.write("\n")


def main() -> None:
    args = parse_args()
    links = read_links(args.inputs)

    categorized: Dict[str, List[str]] = defaultdict(list)
    for link in links:
        category = categorize(link)
        categorized[category].append(link)

    # Deduplicate each category while preserving order
    for key, values in list(categorized.items()):
        categorized[key] = dedupe_preserve_order(values)

    write_categories(categorized, args.output_dir)

    stats = {
        category: len(categorized.get(category, []))
        for category in CATEGORY_FILENAMES.keys()
    }
    stats["total"] = sum(stats.values())
    args.stats_file.parent.mkdir(parents=True, exist_ok=True)
    args.stats_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
