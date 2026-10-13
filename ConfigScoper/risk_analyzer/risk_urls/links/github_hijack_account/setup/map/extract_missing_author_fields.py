"""Collect fields that reference GitHub URLs whose authors no longer exist."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List


BASE = Path("data/links/github_hijack_account")
URL_REPORT = BASE / "github_url_report.json"
SETUP_FILES = BASE / "setup" / "map" / "setup_files.json"
OUTPUT = BASE / "setup" / "map" / "missing_author_fields.json"


def load_json(path: Path):
    return json.loads(path.read_text())


def main() -> None:
    url_report = load_json(URL_REPORT)
    setup_files = load_json(SETUP_FILES)

    missing_authors = {entry["original_url"] for entry in url_report if entry.get("author_exists") == False}

    results: List[dict] = []
    for file_info in setup_files.values():
        for field_name, field_info in file_info.get("fields", {}).items():
            for url in field_info.get("urls") or []:
                if url in missing_authors:
                    # Keep every occurrence; no deduplication.
                    results.append({"original_url": url, "field": field_name})

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2))
    print(f"Wrote {len(results)} records to {OUTPUT}")


if __name__ == "__main__":
    main()
