from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "missing_package_urls_in_toml_fields.json"
OUTPUT = BASE_DIR / "missing_package_urls_by_field_transport.json"


def transport_of(url: str) -> str:
    """Return transport identifier combining optional VCS prefix and protocol."""
    if url.startswith("git+"):
        raw = url[4:]
        scheme = urlparse(raw).scheme or "unknown"
        return f"git+{scheme}"
    return urlparse(url).scheme or "unknown"


def main() -> None:
    data = json.loads(INPUT.read_text())

    grouped: dict[str, dict[str, dict[str, object]]] = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "urls": []})
    )

    for item in data:
        field = item["field"]
        transport = transport_of(item["url"])
        bucket = grouped[field][transport]
        bucket["count"] += 1
        bucket["urls"].append(item["url"])

    OUTPUT.write_text(json.dumps(grouped, indent=2))
    print(f"Wrote transport breakdown for {len(grouped)} fields to {OUTPUT}")


if __name__ == "__main__":
    main()
