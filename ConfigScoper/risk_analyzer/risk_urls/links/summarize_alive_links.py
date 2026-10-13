#!/usr/bin/env python3
"""
Aggregate alive links across multiple files and split them into protocol buckets.

Categories:
    http, https, git (git://, git+, ssh://), hg, bzr, svn, rest

Outputs:
    * Category files containing deduplicated links.
    * A JSON stats file summarising counts.
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

DEFAULT_INPUTS = (
    Path("data/links/pipfile/alive_urls.txt"),
    Path("data/links/pyproject/alive_urls.txt"),
    Path("data/links/requirements/alive_urls.txt"),
    Path("data/links/setup/alive_urls.txt"),
)

DEFAULT_OUTPUT_DIR = Path("data/links/summary/alive")
DEFAULT_STATS_FILE = DEFAULT_OUTPUT_DIR / "alive_links_stats.json"

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
    parser = argparse.ArgumentParser(description="Summarise alive links by protocol.")
    parser.add_argument(
        "--inputs",
        nargs="*",
        type=Path,
        default=list(DEFAULT_INPUTS),
        help="Alive URL files to process.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write category files.",
    )
    parser.add_argument(
        "--stats-file",
        type=Path,
        default=DEFAULT_STATS_FILE,
        help="Path for JSON summary.",
    )
    return parser.parse_args()


def load_links(paths: Iterable[Path]) -> List[str]:
    links: List[str] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if line and not line.startswith("#"):
                    links.append(line)
    return links


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


def dedupe_preserve(items: Iterable[str]) -> List[str]:
    ordered: Dict[str, None] = OrderedDict()
    for item in items:
        ordered.setdefault(item, None)
    return list(ordered.keys())


def write_categories(data: Dict[str, List[str]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for category, filename in CATEGORY_FILENAMES.items():
        links = data.get(category, [])
        target = output_dir / filename
        with target.open("w", encoding="utf-8") as fh:
            for link in links:
                fh.write(link)
                fh.write("\n")


def main() -> None:
    args = parse_args()
    links = load_links(args.inputs)

    categorized: Dict[str, List[str]] = defaultdict(list)
    for link in links:
        categorized[categorize(link)].append(link)

    for key, values in list(categorized.items()):
        categorized[key] = dedupe_preserve(values)

    write_categories(categorized, args.output_dir)

    stats = {category: len(categorized.get(category, [])) for category in CATEGORY_FILENAMES}
    stats["total"] = sum(stats.values())
    args.stats_file.parent.mkdir(parents=True, exist_ok=True)
    args.stats_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
