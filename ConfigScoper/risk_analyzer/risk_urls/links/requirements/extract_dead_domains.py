#!/usr/bin/env python3
"""Extract domains from data/links/requirements/dead_urls.txt."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_INPUT = Path("data/links/requirements/dead_urls.txt")
DEFAULT_OUTPUT = Path("data/links/requirements/dead_domains.txt")

URL_START_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract unique domains from requirements dead URLs."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path to the dead URLs file (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Where to write the domain list (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def iter_urls(line: str):
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


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    domains: set[str] = set()
    with args.input.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            for url in iter_urls(line):
                domain = extract_domain(url)
                if domain:
                    domains.add(domain)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(sorted(domains)), encoding="utf-8")
    print(f"Wrote {len(domains)} unique domains to {args.output}")


if __name__ == "__main__":
    main()
