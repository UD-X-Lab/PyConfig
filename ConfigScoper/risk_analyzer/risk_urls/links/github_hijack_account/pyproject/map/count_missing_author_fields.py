"""Count field frequencies in missing_author_fields.json."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


INPUT = Path("data/links/github_hijack_account/pyproject/map/missing_author_fields.json")
OUTPUT = Path("data/links/github_hijack_account/pyproject/map/missing_author_field_counts.json")


def main() -> None:
    data = json.loads(INPUT.read_text())
    counter = Counter()
    for entry in data:
        field = entry.get("field")
        if field:
            counter[field] += 1

    # Keep output stable and readable.
    ordered = {field: count for field, count in counter.most_common()}
    OUTPUT.write_text(json.dumps(ordered, indent=2))
    print(f"Counted {len(counter)} unique fields; wrote to {OUTPUT}")


if __name__ == "__main__":
    main()
