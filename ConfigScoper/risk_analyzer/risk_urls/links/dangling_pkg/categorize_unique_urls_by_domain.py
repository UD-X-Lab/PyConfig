from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "missing_package_urls_unique.txt"
OUTPUT = BASE_DIR / "missing_package_urls_unique_by_domain.json"


def extract_domain(url: str) -> str:
    candidate = url.strip()
    if "://" in candidate and "+" in candidate.split("://", 1)[0]:
        candidate = candidate.split("+", 1)[1]
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return "unknown"
    host = parsed.netloc.split("@")[-1].split(":")[0].lower()
    return host or "unknown"


def main() -> None:
    grouped = defaultdict(lambda: {"count": 0, "urls": []})

    for line in INPUT.read_text().splitlines():
        url = line.strip()
        if not url:
            continue
        domain = extract_domain(url)
        grouped[domain]["count"] += 1
        grouped[domain]["urls"].append(url)

    OUTPUT.write_text(json.dumps(grouped, indent=2))
    print(f"Wrote {len(grouped)} domains to {OUTPUT}")


if __name__ == "__main__":
    main()
