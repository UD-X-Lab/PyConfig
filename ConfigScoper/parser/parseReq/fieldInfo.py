import json
from pathlib import Path
from typing import Any, Optional, Dict, Tuple


def _find_key(obj: Any, target: str) -> Optional[Any]:
    if isinstance(obj, dict):
        if target in obj:
            return obj[target]
        for value in obj.values():
            found = _find_key(value, target)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_key(value, target)
            if found is not None:
                return found
    return None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    input_path = base_dir / "output" / "req_statistic.json"
    field_info_dir = base_dir / "output" / "fieldInfo"

    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    mapping: Dict[str, Tuple[str, str]] = {
        "vcs_links": ("R1", "vcsURL.json"),
        "direct_file_links": ("R1", "directURL.json"),
        "find_links_values_top": ("R2", "findLink.json"),
        "index_url_values_top": ("R2", "indexURL.json"),
        "extra_index_url_values_top": ("R2", "extraURL.json"),
        "trusted_host_values_top": ("R2", "trustHost.json"),
    }

    for key, (risk_dir, filename) in mapping.items():
        value = _find_key(data, key)
        if value is None:
            value = {}
        if key == "vcs_links":
            if isinstance(value, dict):
                    value = value.get("raw_examples_top", {})
            else:
                value = {}           
        if key == "direct_file_links":
            if isinstance(value, dict):
                value = value.get("by_url_top", {})
            else:
                value = {}
        out_path = field_info_dir / risk_dir / filename
        _write_json(out_path, value)


if __name__ == "__main__":
    main()
