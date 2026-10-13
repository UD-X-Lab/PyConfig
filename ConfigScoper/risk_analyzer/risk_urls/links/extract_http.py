#!/usr/bin/env python3
"""
extract_http.py

Usage:
    python extract_http.py path/to/file.txt
    cat file.txt | python extract_http.py     # reads stdin if no file provided

Outputs found http:// links (one per line). https:// links are ignored.
"""

import re
import sys
import argparse
from collections import OrderedDict

# Match only http:// (not https)
URL_RE = re.compile(r'http://[^\s\'"<>]+', re.IGNORECASE)
TRAILING_CHARS = '.,;:!?)]}>\'"'

def clean_url(raw: str) -> str:
    """Trim common trailing punctuation and balance parentheses/brackets."""
    u = raw.rstrip()
    while u and u[-1] in TRAILING_CHARS:
        u = u[:-1].rstrip()

    opening = sum(1 for c in u if c in '([{')
    closing = sum(1 for c in u if c in ')]}')
    while closing > opening and u and u[-1] in ')]}':
        u = u[:-1].rstrip()
        closing -= 1

    return u

def extract_urls(text: str):
    """Return list of unique http:// URLs in order of appearance."""
    seen = OrderedDict()
    for m in URL_RE.finditer(text):
        raw = m.group(0)
        url = clean_url(raw)
        if url and url not in seen:
            seen[url] = None
    return list(seen.keys())

def main():
    parser = argparse.ArgumentParser(description="Extract http:// links from text")
    parser.add_argument("file", nargs="?", help="path to text file (reads stdin if omitted)")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    urls = extract_urls(text)
    with open("http_links.txt", "a") as f:
        for u in urls:
            f.write(u)
            f.write("\n")

if __name__ == "__main__":
    main()
