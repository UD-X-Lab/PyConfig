import json
import re
from pathlib import Path
from typing import Any

FIELD_TYPES = ["url", "class", "function", "shell command", "script file"]

URL_PATTERNS = re.compile(
    r"^(?:https?://|git\+|ssh://|ftp://|file://|svn\+|hg\+|bzr\+|git@|https?:\\\\|\./|\../).+",
    re.IGNORECASE,
)
SCRIPT_EXTENSIONS = {"py", "sh", "bat", "cmd", "ps1", "pl", "rb"}

PLACEHOLDERS = {
    "url": "https://github.com/mhammond/pywin32/archive/refs/tags/b306.tar.gz#egg=pywin32",
    "class": "FieldHunter.mutator.real_types.ExampleClass",
    "function": "FieldHunter.mutator.real_types.example_function",
    "shell command": "bash -lc \"echo real_shell_command\"",
    "script file": "FieldHunter/mutator/real_script.py",
}


def read_file(filepath: Path) -> str:
    return filepath.read_text(encoding="utf-8")


def write_file(filepath: Path, content: str) -> None:
    filepath.write_text(content, encoding="utf-8")


def is_url(value: str) -> bool:
    return bool(URL_PATTERNS.match(value.strip()))


def is_script_file(value: str) -> bool:
    value = value.strip()
    if "." not in value:
        return False
    suffix = value.split("#", 1)[0].split("?", 1)[0].rsplit(".", 1)[-1].lower()
    return suffix in SCRIPT_EXTENSIONS


def is_shell_command(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    if value.startswith("!"):
        return True
    if any(token in value for token in ["&&", "||", "|", ";", "$()", "`"]):
        return True
    if re.match(r"^(?:bash|sh|python|python3|cmd|powershell)(?:\s|$)", value):
        return True
    return False


def is_class_reference(value: str) -> bool:
    if "." not in value:
        return False
    value = value.strip().split("#", 1)[0].strip()
    last = value.rsplit(".", 1)[-1]
    return bool(last) and last[0].isupper()


def is_function_reference(value: str) -> bool:
    stripped = value.strip()
    if stripped.endswith("(") or stripped.endswith(")"):
        return True
    if "." in stripped:
        last = stripped.rsplit(".", 1)[-1]
        return bool(last) and last[0].islower() and not stripped.startswith("-")
    return False


def detect_field_type(value: str) -> str | None:
    if not value or value.startswith("-"):
        return None
    if is_url(value):
        return "url"
    if is_script_file(value):
        return "script file"
    if is_shell_command(value):
        return "shell command"
    if is_class_reference(value):
        return "class"
    if is_function_reference(value):
        return "function"
    return None


def build_suspicious_map(value: Any, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    found: dict[tuple[str, ...], str] = {}
    if isinstance(value, str):
        detected = detect_field_type(value)
        if detected is not None:
            found[path] = detected
        return found
    if isinstance(value, dict):
        for key, item in value.items():
            found.update(build_suspicious_map(item, path + (key,)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.update(build_suspicious_map(item, path + (str(index),)))
    return found


def mutate_value(value: Any, target_type: str) -> Any:
    if isinstance(value, str):
        if detect_field_type(value) is not None:
            return value
        return PLACEHOLDERS[target_type]
    if isinstance(value, dict):
        return {k: mutate_value(v, target_type) for k, v in value.items()}
    if isinstance(value, list):
        return [mutate_value(item, target_type) for item in value]
    return value


def json_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def dump_json_with_comments(value: Any, comments: dict[tuple[str, ...], str], path: tuple[str, ...] = (), indent: int = 2, level: int = 0) -> str:
    prefix = " " * (level * indent)
    if isinstance(value, dict):
        lines: list[str] = ["{"]
        items = list(value.items())
        for idx, (key, item) in enumerate(items):
            inner = dump_json_with_comments(item, comments, path + (key,), indent, level + 1)
            comment = f"  # suspicious:{comments[path + (key,)]}" if (path + (key,)) in comments else ""
            sep = "," if idx < len(items) - 1 else ""
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{' ' * indent}{json_literal(key)}: {inner.lstrip()}{sep}{comment}")
            else:
                lines.append(f"{prefix}{' ' * indent}{json_literal(key)}: {inner}{sep}{comment}")
        lines.append(f"{prefix}}}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        lines: list[str] = ["["]
        for idx, item in enumerate(value):
            inner = dump_json_with_comments(item, comments, path + (str(idx),), indent, level + 1)
            comment = f"  # suspicious:{comments[path + (str(idx),)]}" if (path + (str(idx),)) in comments else ""
            sep = "," if idx < len(value) - 1 else ""
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{' ' * indent}{inner.lstrip()}{sep}{comment}")
            else:
                lines.append(f"{prefix}{' ' * indent}{inner}{sep}{comment}")
        lines.append(f"{prefix}]")
        return "\n".join(lines)
    return json_literal(value)


def process_pipfile_lock_file(lock_path: Path) -> dict[str, Any]:
    raw = read_file(lock_path)
    report = {"file": str(lock_path), "suspicious": []}

    try:
        parsed = json.loads(raw)
    except Exception as exc:
        report["parsed"] = False
        report["error"] = str(exc)
        annotated_file = lock_path.with_name(lock_path.stem + "_annotated" + lock_path.suffix)
        write_file(annotated_file, raw)
        return report

    report["parsed"] = True
    suspicious_map = build_suspicious_map(parsed)
    suspicious_items = sorted(suspicious_map.items())
    report["suspicious"] = [("/".join(path), kind) for path, kind in suspicious_items]

    annotated_text = dump_json_with_comments(parsed, suspicious_map)
    annotated_file = lock_path.with_name(lock_path.stem + "_annotated" + lock_path.suffix)
    write_file(annotated_file, annotated_text + "\n")

    for field_type in FIELD_TYPES:
        mutated = mutate_value(parsed, field_type)
        mutated_file = lock_path.with_name(f"{lock_path.stem}_{field_type.replace(' ', '_')}{lock_path.suffix}")
        write_file(mutated_file, json.dumps(mutated, indent=2, ensure_ascii=False) + "\n")

    return report


def scan_pipfile_lock_root(root_path: Path) -> list[dict[str, Any]]:
    root_path = root_path.resolve()
    results: list[dict[str, Any]] = []
    for name in ["Pipfile.lock", "pipfile.lock"]:
        for lock_path in sorted(root_path.rglob(name)):
            if lock_path.is_file():
                results.append(process_pipfile_lock_file(lock_path))
    return results


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Scan Pipfile.lock directories and mutate JSON content with real placeholders.")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Root directory to scan for Pipfile.lock files (default: current directory)",
    )
    args = parser.parse_args()

    root_path = Path(args.root)
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"Root directory not found: {root_path}")

    results = scan_pipfile_lock_root(root_path)
    for result in results:
        print(f"File: {result['file']}")
        if result.get("parsed"):
            if result["suspicious"]:
                for item in result["suspicious"]:
                    print(f"  suspicious entry: path index {item[0]}, type {item[1]}")
            else:
                print("  no suspicious fields detected")
        else:
            print(f"  parse error: {result.get('error')}")


if __name__ == "__main__":
    main()
