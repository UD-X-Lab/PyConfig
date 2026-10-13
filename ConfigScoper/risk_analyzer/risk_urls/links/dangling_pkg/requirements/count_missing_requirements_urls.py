from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "missing_package_requirements_link_sources.json"
OUTPUT = BASE_DIR / "missing_package_requirements_url_counts.json"


def main() -> None:
    data = json.loads(INPUT.read_text())

    counts = {}
    for url, files in data.get("vcs_raw_sources", {}).items():
        counts[url] = len(files)
    for url, files in data.get("direct_file_by_url_sources", {}).items():
        counts[url] = len(files)

    OUTPUT.write_text(json.dumps(counts, indent=2))
    print(f"Wrote counts for {len(counts)} URLs to {OUTPUT}")


if __name__ == "__main__":
    main()
