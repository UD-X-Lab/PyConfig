from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "missing_package_urls_in_toml_fields.json"
OUTPUT = BASE_DIR / "missing_package_urls_field_counts.json"


def main() -> None:
    data = json.loads(INPUT.read_text())
    counter = Counter(item["field"] for item in data)

    OUTPUT.write_text(json.dumps(counter, indent=2))
    print(f"Wrote {len(counter)} field buckets to {OUTPUT}")


if __name__ == "__main__":
    main()
