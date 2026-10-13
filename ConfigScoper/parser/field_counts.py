from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


TARGET_FILES = (
    Path("parser/parseReq/output/fieldInfo/R1/directURL.json"),
    Path("parser/parseReq/output/fieldInfo/R1/vcsURL.json"),
)


def _iter_values(values: Iterable[Any]) -> Iterable[Any]:
    for value in values:
        yield value


def count_urls(data: Any) -> tuple[int, int]:
    if isinstance(data, dict):
        unique = len(data)
        total = 0
        for value in _iter_values(data.values()):
            if isinstance(value, bool):
                total += 1
            elif isinstance(value, (int, float)):
                total += int(value)
            elif value is None:
                total += 0
            elif isinstance(value, (list, tuple, set)):
                total += len(value)
            else:
                total += 1
        return unique, total

    if isinstance(data, (list, tuple, set)):
        size = len(data)
        return size, size

    if data:
        return 1, 1

    return 0, 0


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    for path in TARGET_FILES:
        data = load_json(path)
        unique, total = count_urls(data)
        print(f"{path}: unique_urls={unique}, total_urls={total}")


if __name__ == "__main__":
    main()
