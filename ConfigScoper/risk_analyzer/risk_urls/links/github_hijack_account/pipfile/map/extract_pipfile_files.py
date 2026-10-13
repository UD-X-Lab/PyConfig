"""Extract the `files` section from pipfile_stats.json."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = Path("data/links/github_hijack_account/pipfile/pipfile_stats.json")
TARGET = Path("data/links/github_hijack_account/pipfile/map/pipfile_files.json")


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source file not found: {SOURCE}")

    data = json.loads(SOURCE.read_text())
    files = data.get("files")
    if files is None:
        raise KeyError("`files` field missing in source JSON")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(files, indent=2))
    print(f"Wrote {len(files)} entries to {TARGET}")


if __name__ == "__main__":
    main()
