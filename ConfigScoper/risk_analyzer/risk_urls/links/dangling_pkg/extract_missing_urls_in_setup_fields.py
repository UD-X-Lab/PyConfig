from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).parent
MISSING_INPUT = BASE_DIR / "package_url_report_missing_packages.json"
SETUP_INPUT = BASE_DIR.parent / "github_hijack_account" / "setup" / "map" / "setup_files.json"
OUTPUT = BASE_DIR / "missing_package_urls_in_setup_fields.json"


def iter_strings(obj) -> Iterable[str]:
    """Yield all string values contained in arbitrarily nested structures."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from iter_strings(value)
    elif isinstance(obj, (list, tuple, set)):
        for value in obj:
            yield from iter_strings(value)


def main() -> None:
    missing_data = json.loads(MISSING_INPUT.read_text())
    target_urls = {item["original_url"] for item in missing_data}

    setup_data = json.loads(SETUP_INPUT.read_text())

    results = []
    for setup_file, setup_info in setup_data.items():
        fields = setup_info.get("fields", {})
        for field_name, field_info in fields.items():
            all_strings = list(iter_strings(field_info))
            for url in target_urls:
                if any(url in value for value in all_strings):
                    results.append(
                        {
                            "setup_file": setup_file,
                            "field": field_name,
                            "url": url,
                        }
                    )

    OUTPUT.write_text(json.dumps(results, indent=2))
    print(f"Wrote {len(results)} matches to {OUTPUT}")


if __name__ == "__main__":
    main()
