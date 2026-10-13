from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "missing_package_urls_in_setup_fields.json"
OUTPUT = BASE_DIR / "missing_package_urls_by_domain.json"


def main() -> None:
    data = json.loads(INPUT.read_text())

    grouped = defaultdict(lambda: {"count": 0, "entries": []})

    for item in data:
        url = item["url"]
        domain = urlparse(url).netloc or "unknown"
        grouped[domain]["count"] += 1
        grouped[domain]["entries"].append(
            {
                "url": url,
                "setup_file": item["setup_file"],
                "field": item["field"],
            }
        )

    OUTPUT.write_text(json.dumps(grouped, indent=2))
    print(f"Wrote {len(grouped)} domains to {OUTPUT}")


if __name__ == "__main__":
    main()
