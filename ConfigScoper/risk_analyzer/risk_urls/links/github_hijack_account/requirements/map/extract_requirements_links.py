"""Extract VCS raw sources and direct file link sources into a single JSON."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = Path("data/fields/requirements/requirements_statistics.json")
TARGET = Path("data/links/github_hijack_account/requirements/map/requirements_link_sources.json")


def main() -> None:
    data = json.loads(SOURCE.read_text())

    vcs_raw_sources = data.get("vcs_links", {}).get("raw_sources", {})
    direct_file_by_url_sources = data.get("direct_file_links", {}).get("by_url_sources", {})

    output = {
        "vcs_raw_sources": vcs_raw_sources,
        "direct_file_by_url_sources": direct_file_by_url_sources,
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(output, indent=2))
    print(f"Wrote extracted data to {TARGET}")


if __name__ == "__main__":
    main()
