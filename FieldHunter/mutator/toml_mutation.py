import argparse
import re
from pathlib import Path
from typing import Any

try:
    import tomllib  # type: ignore
    toml_loads = lambda s: tomllib.loads(s)
except Exception:
    import tomli  # type: ignore
    toml_loads = lambda s: tomli.loads(s)

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


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


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
    suspicious: dict[tuple[str, ...], str] = {}
    if isinstance(value, str):
        detected = detect_field_type(value)
        if detected is not None:
            suspicious[path] = detected
        return suspicious
    if isinstance(value, dict):
        for key, item in value.items():
            suspicious.update(build_suspicious_map(item, path + (key,)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            suspicious.update(build_suspicious_map(item, path + (str(index),)))
    return suspicious


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


def toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    escaped = key.replace('"', '\\"')
    return f'"{escaped}"'


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return toml_string(value)
    if isinstance(value, list):
        items = ", ".join(render_value(item) for item in value)
        return f"[{items}]"
    if isinstance(value, dict):
        items = ", ".join(f"{toml_key(k)} = {render_value(v)}" for k, v in value.items())
        return f"{{{items}}}"
    raise TypeError(f"Unsupported TOML value type: {type(value)}")


def find_comment(path: tuple[str, ...], comments: dict[tuple[str, ...], str]) -> str | None:
    return comments.get(path)


def dump_toml(obj: Any, comments: dict[tuple[str, ...], str] | None = None, path: tuple[str, ...] = (), level: int = 0) -> str:
    indent = "  "
    prefix = indent * level
    comments = comments or {}

    if isinstance(obj, dict):
        lines: list[str] = []
        simple_keys = []
        table_keys = []
        array_table_keys = []
        for key, value in obj.items():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                array_table_keys.append((key, value))
            elif isinstance(value, dict):
                table_keys.append((key, value))
            else:
                simple_keys.append((key, value))

        for key, value in simple_keys:
            line = f"{toml_key(key)} = {render_value(value)}"
            if comment := find_comment(path + (key,), comments):
                line += f"  # suspicious:{comment}"
            lines.append(prefix + line)

        for key, value in table_keys:
            header = ".".join(path + (key,))
            if lines:
                lines.append("")
            lines.append(f"[{header}]")
            lines.append(dump_toml(value, comments, path + (key,), level=0))

        for key, value in array_table_keys:
            if lines:
                lines.append("")
            for item in value:
                header = ".".join(path + (key,))
                lines.append(f"[[{header}]]")
                lines.append(dump_toml(item, comments, path + (key,), level=0))

        return "\n".join(lines)

    if isinstance(obj, list):
        if not obj:
            return "[]"
        if all(not isinstance(item, (dict, list)) for item in obj):
            rendered = "[" + ", ".join(render_value(item) for item in obj) + "]"
            if comment := next((comments[path + (str(idx),)] for idx in range(len(obj)) if path + (str(idx),) in comments), None):
                return f"{rendered}  # suspicious:{comment}"
            return rendered
        lines = ["["]
        for idx, item in enumerate(obj):
            item_path = path + (str(idx),)
            item_text = dump_toml(item, comments, item_path, level + 1)
            if isinstance(item, (dict, list)):
                lines.append(item_text)
            else:
                line = prefix + indent + item_text
                if comment := find_comment(item_path, comments):
                    line += f"  # suspicious:{comment}"
                lines.append(line)
        lines.append(prefix + "]")
        return "\n".join(lines)

    return render_value(obj)


def process_pyproject_file(pyproject_path: Path) -> dict[str, Any]:
    raw = read_file(pyproject_path)
    report: dict[str, Any] = {"file": str(pyproject_path), "suspicious": []}

    try:
        parsed = toml_loads(raw)
    except Exception as exc:
        report["parsed"] = False
        report["error"] = str(exc)
        annotated_file = pyproject_path.with_name(pyproject_path.stem + "_annotated" + pyproject_path.suffix)
        write_file(annotated_file, raw)
        return report

    report["parsed"] = True
    suspicious_map = build_suspicious_map(parsed)
    report["suspicious"] = [("/".join(path), kind) for path, kind in sorted(suspicious_map.items())]

    annotated_text = dump_toml(parsed, suspicious_map)
    annotated_file = pyproject_path.with_name(pyproject_path.stem + "_annotated" + pyproject_path.suffix)
    write_file(annotated_file, annotated_text + "\n")

    for field_type in FIELD_TYPES:
        mutated = mutate_value(parsed, field_type)
        mutated_file = pyproject_path.with_name(f"{pyproject_path.stem}_{field_type.replace(' ', '_')}{pyproject_path.suffix}")
        write_file(mutated_file, dump_toml(mutated) + "\n")

    return report


def scan_pyproject_root(root_path: Path) -> list[dict[str, Any]]:
    root_path = root_path.resolve()
    results: list[dict[str, Any]] = []
    for path in sorted(root_path.rglob("*")):
        if path.is_file() and path.name.lower() == "pyproject.toml":
            results.append(process_pyproject_file(path))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan pyproject.toml directories and mutate values with real placeholder types.")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Root directory to scan for pyproject.toml files (default: current directory)",
    )
    args = parser.parse_args()

    root_path = Path(args.root)
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"Root directory not found: {root_path}")

    results = scan_pyproject_root(root_path)
    for result in results:
        print(f"File: {result['file']}")
        if not result.get("parsed"):
            print(f"  parse error: {result.get('error')}")
            continue
        if result["suspicious"]:
            for path, kind in result["suspicious"]:
                print(f"  suspicious field: {path}, type {kind}")
        else:
            print("  no suspicious fields detected")


if __name__ == "__main__":
    main()
