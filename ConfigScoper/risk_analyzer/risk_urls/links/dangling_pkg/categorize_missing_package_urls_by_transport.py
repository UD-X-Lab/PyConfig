from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "missing_package_urls_in_setup_fields.json"
OUTPUT = BASE_DIR / "missing_package_urls_by_transport.json"


def transport_of(url: str) -> str:
    """Return transport identifier combining optional VCS prefix and protocol."""
    if url.startswith("git+"):
        raw = url[4:]
        scheme = urlparse(raw).scheme or "unknown"
        return f"git+{scheme}"
    return urlparse(url).scheme or "unknown"


def main() -> None:
    data = json.loads(INPUT.read_text())
    grouped = defaultdict(lambda: {"count": 0, "entries": []})

    for item in data:
        transport = transport_of(item["url"])
        grouped[transport]["count"] += 1
        grouped[transport]["entries"].append(
            {
                "url": item["url"],
                "setup_file": item["setup_file"],
                "field": item["field"],
            }
        )

    OUTPUT.write_text(json.dumps(grouped, indent=2))
    print(f"Wrote {len(grouped)} transports to {OUTPUT}")


if __name__ == "__main__":
    main()
