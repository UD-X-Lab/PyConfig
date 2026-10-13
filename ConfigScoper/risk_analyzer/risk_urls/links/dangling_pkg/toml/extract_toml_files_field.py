from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).parent
INPUT = Path("data/links/github_hijack_account/pyproject/toml_field_stats.json")
OUTPUT = BASE_DIR / "toml_files.json"


def main() -> None:
    data = json.loads(INPUT.read_text())
    files_section = data.get("files", {})

    OUTPUT.write_text(json.dumps(files_section, indent=2))
    print(f"Wrote {len(files_section)} file entries to {OUTPUT}")


if __name__ == "__main__":
    main()
