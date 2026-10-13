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
    input_path = base_dir / "output" / "setup_statistic.json"
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

    r1_dir = field_info_dir / "R1"
    c1_dir = field_info_dir / "C1"
    c2_dir = field_info_dir / "C2"
    c4_dir = field_info_dir / "C4"
    for d in (r1_dir, c1_dir, c2_dir, c4_dir):
        d.mkdir(parents=True, exist_ok=True)

    extras_dir = r1_dir / "extrasRequire"
    extras_dir.mkdir(parents=True, exist_ok=True)

    file_to_targets: Dict[str, list] = {}

    def add_targets(filename: str, *targets: Path) -> None:
        file_to_targets.setdefault(filename, []).extend(targets)

    add_targets("install_requires.json", r1_dir)
    add_targets("tests_require.json", r1_dir)
    add_targets("dependency_links.json", r1_dir)

    add_targets("cmdclass.json", c1_dir)
    add_targets("distclass.json", c1_dir)
    add_targets("ext_modules.json", c1_dir)
    add_targets("ext_package.json", c1_dir)

    add_targets("scripts.json", c2_dir)

    add_targets("test_loader.json", c4_dir)
    add_targets("test_runner.json", c4_dir)
    add_targets("test_suite.json", c4_dir)

    for extras_path in field_info_dir.glob("extras_require*.json"):
        add_targets(extras_path.name, extras_dir)

    for filename, targets in file_to_targets.items():
        src = field_info_dir / filename
        if not src.exists():
            continue
        payload = src.read_bytes()
        for target_dir in targets:
            dst = target_dir / filename
            dst.write_bytes(payload)
        src.unlink()

if __name__ == "__main__":
    # genSingleFieldInfoFile()
    fieldMapRisk()
