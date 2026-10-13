from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Set


BASE_DIR = Path(__file__).parent

INPUT_FILES = [
    BASE_DIR / "missing_package_urls_in_setup_fields.json",
    BASE_DIR / "toml" / "missing_package_urls_in_toml_fields.json",
    BASE_DIR / "requirements" / "missing_package_requirements_url_counts.json",
    BASE_DIR / "pipfile" / "missing_package_urls_in_pipfile_fields.json",
]

OUTPUT = BASE_DIR / "missing_package_urls_unique.txt"


def iter_urls_from_obj(obj) -> Iterable[str]:
    if isinstance(obj, dict):
        if "url" in obj and isinstance(obj["url"], str):
            yield obj["url"]
        else:
            for key, value in obj.items():
                if isinstance(key, str) and key.startswith(("http://", "https://", "git+", "ssh://")):
                    yield key
                yield from iter_urls_from_obj(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_urls_from_obj(item)


def main() -> None:
    urls: Set[str] = set()
    for path in INPUT_FILES:
        data = json.loads(path.read_text())
        urls.update(iter_urls_from_obj(data))

    OUTPUT.write_text("\n".join(sorted(urls)) + "\n")
    print(f"Wrote {len(urls)} unique URLs to {OUTPUT}")


if __name__ == "__main__":
    main()
