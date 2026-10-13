from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).parent
MISSING_INPUT = BASE_DIR.parent / "package_url_report_missing_packages.json"
REQ_SOURCES_INPUT = (
    BASE_DIR.parent.parent
    / "github_hijack_account"
    / "requirements"
    / "map"
    / "requirements_link_sources.json"
)
OUTPUT = BASE_DIR / "missing_package_requirements_link_sources.json"


def main() -> None:
    missing_data = json.loads(MISSING_INPUT.read_text())
    target_urls = {item["original_url"] for item in missing_data}

    req_sources = json.loads(REQ_SOURCES_INPUT.read_text())

    filtered = {}
    for key in ("vcs_raw_sources", "direct_file_by_url_sources"):
        section = req_sources.get(key, {})
        filtered[key] = {url: files for url, files in section.items() if url in target_urls}

    OUTPUT.write_text(json.dumps(filtered, indent=2))
    matched_count = sum(len(section) for section in filtered.values())
    print(f"Wrote {matched_count} matched URLs to {OUTPUT}")


if __name__ == "__main__":
    main()
