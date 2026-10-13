#!/usr/bin/env python3
"""
Extract unique domains from multiple URL list files.

Usage:
    python data/links/extract_domains.py \
        --inputs data/links/pipfile/dead_urls.txt data/links/pipfile/invalid_urls.txt \
        --output data/links/domain_summary.json

By default the script will process the eight standard files from pipfile/setup/
pyproject/requirements (both dead_urls.txt and invalid_urls.txt) and write the
results to data/links/domain_summary.json as well as a plain text list.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set
from urllib.parse import urlparse

DEFAULT_INPUTS = [
    Path("data/links/pipfile/dead_urls.txt"),
    Path("data/links/setup/dead_urls.txt"),
    Path("data/links/pyproject/dead_urls.txt"),
    Path("data/links/requirements/dead_urls.txt"),
    Path("data/links/pipfile/invalid_urls.txt"),
    Path("data/links/setup/invalid_urls.txt"),
    Path("data/links/pyproject/invalid_urls.txt"),
    Path("data/links/requirements/invalid_urls.txt"),
]

DEFAULT_JSON_OUTPUT = Path("data/links/domain_takeover/domain_summary.json")
DEFAULT_TEXT_OUTPUT = Path("data/links/domain_takeover/domain_summary.txt")

# Generic URL prefix pattern (same as check_domain_expiry)
URL_START_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract domains from URL lists.")
    parser.add_argument(
        "--inputs",
        nargs="*",
        type=Path,
        default=DEFAULT_INPUTS,
        help="Input files containing URLs (default: standard dead/invalid lists).",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help="Path to write JSON summary (default: data/links/domain_summary.json).",
    )
    parser.add_argument(
        "--text-output",
        type=Path,
        default=DEFAULT_TEXT_OUTPUT,
        help="Path to write newline-separated domains (default: data/links/domain_summary.txt).",
    )
    return parser.parse_args()


def iter_urls(line: str) -> Iterable[str]:
    matches = list(URL_START_RE.finditer(line))
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
        raw_url = line[start:end].strip().strip("'\"`")
        raw_url = raw_url.rstrip(",;)")
        if raw_url:
            yield raw_url


def extract_domain(url: str) -> str | None:
    candidate = url
    if "+" in candidate.split("://", 1)[0]:
        candidate = candidate.split("+", 1)[1]

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None

    if parsed.netloc:
        host = parsed.netloc.split("@")[-1].split(":", 1)[0].lower()
        return host or None

    if "@" in candidate and ":" in candidate.split("@")[-1]:
        return candidate.split("@", 1)[-1].split(":", 1)[0].lower()
    return None


def collect_domains(path: Path) -> Set[str]:
    domains: Set[str] = set()
    if not path.exists():
        return domains

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            for url in iter_urls(line):
                domain = extract_domain(url)
                if domain:
                    domains.add(domain)
    return domains


def main() -> None:
    args = parse_args()
    domain_to_sources: Dict[str, Set[str]] = {}

    for input_path in args.inputs:
        domains = collect_domains(input_path)
        for domain in domains:
            domain_to_sources.setdefault(domain, set()).add(str(input_path))

    unique_domains = sorted(domain_to_sources.keys())

    # Write JSON summary
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(
            {
                "count": len(unique_domains),
                "domains": unique_domains,
                "sources": {
                    domain: sorted(paths)
                    for domain, paths in domain_to_sources.items()
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Write simple text list
    args.text_output.write_text("\n".join(unique_domains), encoding="utf-8")

    print(f"Extracted {len(unique_domains)} unique domains from {len(args.inputs)} files.")


if __name__ == "__main__":
    main()
