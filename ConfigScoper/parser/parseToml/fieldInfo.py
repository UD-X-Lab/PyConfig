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
    input_path = base_dir / "output" / "toml_statistic.json"
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
    r2_dir = field_info_dir / "R2"
    c1_dir = field_info_dir / "C1"
    c2_dir = field_info_dir / "C2"
    c3_dir = field_info_dir / "C3"
    m1_dir = field_info_dir / "M1"
    for d in (r1_dir, r2_dir, c1_dir, c2_dir, c3_dir, m1_dir):
        d.mkdir(parents=True, exist_ok=True)

    c2_poetry_plugin = c2_dir / "poetryPlugin"
    c3_poetry_plugin = c3_dir / "poetryPlugin"
    c2_poetry_plugin.mkdir(parents=True, exist_ok=True)
    c3_poetry_plugin.mkdir(parents=True, exist_ok=True)

    file_to_targets: Dict[str, list] = {}

    def add_targets(filename: str, *targets: Path) -> None:
        file_to_targets.setdefault(filename, []).extend(targets)

    add_targets("build-system.requires.json", r1_dir)
    add_targets("dependency-groups.json", r1_dir)
    add_targets("project.dependencies.json", r1_dir)
    add_targets("project.optional-dependencies.json", r1_dir)
    add_targets("tool.poetry.dependencies.json", r1_dir)
    add_targets("tool.poetry.dev-dependencies.json", r1_dir)

    add_targets("tool.poetry.source_0_.url.json", r2_dir)
    add_targets("tool.poetry.source_1_.url.json", r2_dir)
    add_targets("tool.poetry.source.json", r2_dir)

    add_targets("build-system.backend-path.json", c1_dir)
    add_targets("build-system.build-backend.json", c1_dir)

    add_targets("project.scripts.json", c2_dir, c3_dir)
    add_targets("project.entry-points.json", c2_dir, c3_dir)
    add_targets("tool.setuptools.script-files.json", c2_dir)
    add_targets("tool.poetry.scripts.json", c2_dir, c3_dir, m1_dir)

    for plugin_path in field_info_dir.glob("tool.poetry.plugins*.json"):
        add_targets(plugin_path.name, c2_poetry_plugin, c3_poetry_plugin)

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
