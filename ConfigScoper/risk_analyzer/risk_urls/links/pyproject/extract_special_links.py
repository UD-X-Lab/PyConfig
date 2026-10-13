#!/usr/bin/env python3
"""
Filter invalid URLs by special substrings (localhost, ${PROJECT_ROOT}, etc.).

Reads data/links/pyproject/invalid_urls.txt and writes entries containing any of the
configured markers to data/links/pyproject/special_invalid_urls.txt, while also
writing the remaining entries to a companion file if desired.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Tuple

DEFAULT_INPUT = Path("data/links/pyproject/invalid_urls.txt")
DEFAULT_MATCH_OUTPUT = Path("data/links/pyproject/special_invalid_urls.txt")
DEFAULT_REST_OUTPUT = Path("data/links/pyproject/clean_invalid_urls.txt")

MARKERS = ("localhost", "${PROJECT_ROOT}", "sqlite:", "py://", "gh://")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract invalid URLs containing special markers.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input invalid URL list.")
    parser.add_argument("--match-output", type=Path, default=DEFAULT_MATCH_OUTPUT, help="File to write matched URLs.")
    parser.add_argument("--rest-output", type=Path, default=DEFAULT_REST_OUTPUT, help="File to write remaining URLs.")
    return parser.parse_args()


def partition_lines(path: Path, markers: Iterable[str]) -> Tuple[list[str], list[str]]:
    matched: list[str] = []
    rest: list[str] = []

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            if any(marker in line for marker in markers):
                matched.append(line)
            else:
                rest.append(line)
    return matched, rest


def write_lines(path: Path, lines: Iterable[str]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line)
            fh.write("\n")


def main() -> None:
    args = parse_args()
    matched, rest = partition_lines(args.input, MARKERS)
    write_lines(args.match_output, matched)
    write_lines(args.rest_output, rest)


if __name__ == "__main__":
    main()
