from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "package_url_report.json"
OUTPUT = BASE_DIR / "package_url_report_missing_packages.json"


def main() -> None:
    data = json.loads(INPUT.read_text())
    filtered = [
        item
        for item in data
        if item.get("domain_exists") is True and item.get("package_exists") is False
    ]

    OUTPUT.write_text(json.dumps(filtered, indent=2))
    print(f"Wrote {len(filtered)} items to {OUTPUT}")


if __name__ == "__main__":
    main()
