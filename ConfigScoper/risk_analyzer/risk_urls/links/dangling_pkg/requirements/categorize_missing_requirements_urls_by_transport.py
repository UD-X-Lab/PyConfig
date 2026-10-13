from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "missing_package_requirements_link_sources.json"
OUTPUT = BASE_DIR / "missing_package_requirements_urls_by_transport.json"


def transport_of(url: str) -> str:
    """Return transport identifier combining optional VCS prefix and protocol."""
    if url.startswith("git+"):
        raw = url[4:]
        scheme = urlparse(raw).scheme or "unknown"
        return f"git+{scheme}"
    return urlparse(url).scheme or "unknown"


def main() -> None:
    data = json.loads(INPUT.read_text())

    summary: dict[str, dict[str, int]] = {}

    for section in ("vcs_raw_sources", "direct_file_by_url_sources"):
        for url, files in data.get(section, {}).items():
            transport = transport_of(url)
            bucket = summary.setdefault(transport, {"url_count": 0, "file_count": 0})
            bucket["url_count"] += 1
            bucket["file_count"] += len(files)

    OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {len(summary)} transport buckets to {OUTPUT}")


if __name__ == "__main__":
    main()
