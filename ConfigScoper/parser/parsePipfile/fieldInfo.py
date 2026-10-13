import json
import re
import hashlib
from pathlib import Path
from typing import Dict, Any


def _make_filename(field: str, used: set) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", field).strip("_")
    if not safe:
        safe = "field"
    filename = f"{safe}.json"
    if filename in used:
        short = hashlib.sha1(field.encode("utf-8")).hexdigest()[:8]
        filename = f"{safe}__{short}.json"
        idx = 2
        while filename in used:
            filename = f"{safe}__{short}_{idx}.json"
            idx += 1
    used.add(filename)
    return filename


def genSingleFieldInfoFile() -> None:
    base_dir = Path(__file__).resolve().parent
    input_path = base_dir / "output" / "pipfile_statistic.json"
    output_dir = base_dir / "output" / "fieldInfo"
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    field_counts: Dict[str, int] = data.get("field_counts", {})
    files_data: Dict[str, Any] = data.get("files", {})

    field_to_files: Dict[str, Dict[str, Any]] = {}
    for file_path, info in files_data.items():
        fields = info.get("fields", {})
        for field, field_info in fields.items():
            field_to_files.setdefault(field, {})[file_path] = field_info

    used_filenames = set()
    for field, count in field_counts.items():
        result = {
            "field": field,
            "count": count,
            "files": field_to_files.get(field, {}),
        }
        filename = _make_filename(field, used_filenames)
        out_path = output_dir / filename
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

def fieldMapRisk():
    base_dir = Path(__file__).resolve().parent
    field_info_dir = base_dir / "output" / "fieldInfo"
    field_info_dir.mkdir(parents=True, exist_ok=True)

    risk_dirs = {
        "R1": [
            "pipfile.dev-packages.json",
            "pipfile.packages.json",
        ],
        "R2": [
            "pipfile.source.url.json",
        ],
        "C3": [
            "pipfile.scripts.json",
        ],
        "M1": [
            "pipfile.scripts.json",
        ],
    }

    file_to_dirs: Dict[str, list] = {}
    for dir_name, filenames in risk_dirs.items():
        (field_info_dir / dir_name).mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            file_to_dirs.setdefault(filename, []).append(dir_name)

    for filename, dir_names in file_to_dirs.items():
        src = field_info_dir / filename
        if not src.exists():
            continue
        payload = src.read_bytes()
        for dir_name in dir_names:
            dst = field_info_dir / dir_name / filename
            dst.write_bytes(payload)
        src.unlink()


if __name__ == "__main__":
    # genSingleFieldInfoFile()
    fieldMapRisk()
