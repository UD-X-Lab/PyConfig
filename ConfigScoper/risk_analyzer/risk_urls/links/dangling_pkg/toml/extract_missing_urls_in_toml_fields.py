from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).parent
MISSING_INPUT = BASE_DIR.parent / "package_url_report_missing_packages.json"
TOML_FILES_INPUT = BASE_DIR / "toml_files.json"
OUTPUT = BASE_DIR / "missing_package_urls_in_toml_fields.json"


def iter_strings(obj) -> Iterable[str]:
    """Yield every string value found within a nested structure."""
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

    toml_files = json.loads(TOML_FILES_INPUT.read_text())

    results = []
    for toml_path, info in toml_files.items():
        fields = info.get("fields", {})
        for field_name, field_info in fields.items():
            for value in iter_strings(field_info):
                if value in target_urls:
                    results.append(
                        {
                            "toml_file": toml_path,
                            "field": field_name,
                            "url": value,
                        }
                    )

    OUTPUT.write_text(json.dumps(results, indent=2))
    print(f"Wrote {len(results)} matches to {OUTPUT}")


if __name__ == "__main__":
    main()
