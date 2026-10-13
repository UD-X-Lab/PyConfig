"""Group missing-author requirement URLs by transport (vcs+protocol) and sum counts."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


INPUT = Path("data/links/github_hijack_account/requirements/map/missing_author_link_counts.json")
OUTPUT = Path("data/links/github_hijack_account/requirements/map/missing_author_link_counts_by_transport.json")


def transport_of(url: str) -> str:
    """Return transport identifier combining VCS prefix and protocol."""
    if url.startswith("git+"):
        raw = url[4:]
        scheme = urlparse(raw).scheme or "unknown"
        return f"git+{scheme}"
    scheme = urlparse(url).scheme or "unknown"
    return scheme


def main() -> None:
    data = json.loads(INPUT.read_text())
    totals = {}
    for item in data:
        transport = transport_of(item["url"])
        totals[transport] = totals.get(transport, 0) + item.get("count", 0)

    OUTPUT.write_text(json.dumps(totals, indent=2))
    print(f"Wrote {len(totals)} transport buckets to {OUTPUT}")


if __name__ == "__main__":
    main()
