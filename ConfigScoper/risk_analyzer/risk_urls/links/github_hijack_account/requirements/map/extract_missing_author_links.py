"""Find missing-author URLs present in requirements link sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


BASE = Path("data/links/github_hijack_account")
URL_REPORT = BASE / "github_url_report.json"
LINK_SOURCES = BASE / "requirements" / "map" / "requirements_link_sources.json"
OUTPUT = BASE / "requirements" / "map" / "missing_author_link_counts.json"


def load_json(path: Path):
    return json.loads(path.read_text())


def main() -> None:
    url_report: List[Dict] = load_json(URL_REPORT)
    link_sources: Dict = load_json(LINK_SOURCES)

    missing_authors = {entry["original_url"] for entry in url_report if entry.get("author_exists") is False}

    results: List[Dict] = []

    for section in ("vcs_raw_sources", "direct_file_by_url_sources"):
        urls_map: Dict = link_sources.get(section, {})
        for url, files in urls_map.items():
            if url in missing_authors:
                results.append(
                    {
                        "url": url,
                        "count": len(files),
                        "source": section,
                    }
                )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2))
    print(f"Wrote {len(results)} records to {OUTPUT}")


if __name__ == "__main__":
    main()
