#!/usr/bin/env python3
"""
Split `invalid_urls.txt` links into git (git://), git+ssh, and everything else.

Usage examples:
    python extract_git_protocol_links.py
    python extract_git_protocol_links.py --input custom.txt \
        --git-output data/links/setup/git_git_protocol_urls.txt \
        --git-ssh-output data/links/setup/git_ssh_protocol_urls.txt \
        --rest-output data/links/setup/non_git_protocol_urls.txt
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path

DEFAULT_INPUT = Path("data/links/setup/invalid_urls.txt")
DEFAULT_GIT_OUTPUT = Path("data/links/setup/git_git_protocol_urls.txt")
DEFAULT_GIT_SSH_OUTPUT = Path("data/links/setup/git_ssh_protocol_urls.txt")
DEFAULT_REST_OUTPUT = Path("data/links/setup/non_git_protocol_urls.txt")
DEFAULT_FINAL_INVALID_OUTPUT = Path("data/links/setup/final_invalid_urls.txt")

GIT_PROTOCOL_PREFIXES = ("git+git://", "git://")
GIT_SSH_PREFIX = "git+ssh://"
FILE_LOCALHOST_PREFIX = "file://localhost/{}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract git/git+ssh links and split them into separate files.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Input file containing URLs.",
    )
    parser.add_argument(
        "--git-output",
        type=Path,
        default=DEFAULT_GIT_OUTPUT,
        help="Output file for git-protocol links (git://, git+git://).",
    )
    parser.add_argument(
        "--git-ssh-output",
        type=Path,
        default=DEFAULT_GIT_SSH_OUTPUT,
        help="Output file for git+ssh links.",
    )
    parser.add_argument(
        "--rest-output",
        type=Path,
        default=DEFAULT_REST_OUTPUT,
        help="Output file for all other links.",
    )
    parser.add_argument(
        "--final-invalid-output",
        type=Path,
        default=DEFAULT_FINAL_INVALID_OUTPUT,
        help="Output file for invalid local file URLs (file://localhost/{}...).",
    )
    return parser.parse_args()


def classify_links(path: Path) -> tuple[list[str], list[str], list[str], list[str]]:
    git_links: list[str] = []
    git_ssh_links: list[str] = []
    rest_links: list[str] = []
    local_file_links: list[str] = []

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(GIT_PROTOCOL_PREFIXES):
                git_links.append(line)
            elif line.startswith(GIT_SSH_PREFIX):
                git_ssh_links.append(line)
            elif line.startswith(FILE_LOCALHOST_PREFIX):
                local_file_links.append(line)
            else:
                rest_links.append(line)

    return git_links, git_ssh_links, rest_links, local_file_links


def dedupe(items: list[str]) -> list[str]:
    ordered = OrderedDict()
    for item in items:
        ordered.setdefault(item, None)
    return list(ordered.keys())


def write_list(path: Path, items: list[str]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(item)
            fh.write("\n")


def main() -> None:
    args = parse_args()
    git_links, git_ssh_links, rest_links, invalid_links = classify_links(args.input)

    write_list(args.git_output, dedupe(git_links))
    write_list(args.git_ssh_output, dedupe(git_ssh_links))
    write_list(args.rest_output, dedupe(rest_links))
    write_list(args.final_invalid_output, dedupe(invalid_links))


if __name__ == "__main__":
    main()
