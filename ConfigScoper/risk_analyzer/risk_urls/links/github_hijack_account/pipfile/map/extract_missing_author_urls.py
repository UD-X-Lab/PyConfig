"""Find missing-author GitHub URLs that appear in pipfile files data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set


BASE = Path("data/links/github_hijack_account")
URL_REPORT = BASE / "github_url_report.json"
PIPFILE_FILES = BASE / "pipfile" / "map" / "pipfile_files.json"
OUTPUT = BASE / "pipfile" / "map" / "missing_author_urls.json"


def load_json(path: Path):
    return json.loads(path.read_text())


def collect_pipfile_urls(files_data: Dict) -> Set[str]:
    urls: Set[str] = set()
    for file_info in files_data.values():
        for field_info in file_info.get("fields", {}).values():
            urls.update(field_info.get("urls") or [])
    return urls


def main() -> None:
    url_report: List[Dict] = load_json(URL_REPORT)
    pipfile_files: Dict = load_json(PIPFILE_FILES)

    pipfile_urls = collect_pipfile_urls(pipfile_files)

    results: List[Dict] = []
    for entry in url_report:
        url = entry.get("original_url")
        if entry.get("author_exists") is False and url in pipfile_urls:
            for file_info in pipfile_files.values():
                for field_name, field_info in file_info.get("fields", {}).items():
                    if url in (field_info.get("urls") or []):
                        # Keep every occurrence; no deduplication.
                        results.append({"original_url": url, "field": field_name})

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2))
    print(f"Wrote {len(results)} records to {OUTPUT}")


if __name__ == "__main__":
    main()
