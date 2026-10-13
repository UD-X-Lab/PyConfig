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


def read_file(filepath: Path) -> str:
    return filepath.read_text(encoding="utf-8")


def write_file(filepath: Path, content: str) -> None:
    filepath.write_text(content, encoding="utf-8")


def split_line_comment(line: str) -> tuple[str, str]:
    stripped = line.rstrip("\n")
    if stripped.lstrip().startswith("#"):
        return stripped, ""

    for match in re.finditer(r"(?<!\\\\)#", stripped):
        idx = match.start()
        prefix = stripped[:idx]
        if prefix.endswith("\\"):
            continue
        if prefix.count("\"") % 2 == 0 and prefix.count("\'") % 2 == 0:
            return prefix.rstrip(), stripped[idx:]
    return stripped, ""


def extract_quoted_strings(text: str) -> list[str]:
    strings = []
    for match in re.finditer(r'(?<!\\)(?:"([^"]*)"|\'([^\']*)\')', text):
        strings.append(match.group(1) if match.group(1) is not None else match.group(2))
    return strings


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


def annotate_line(line: str) -> tuple[str, str | None]:
    content, comment = split_line_comment(line)
    if not content.strip() or content.lstrip().startswith("#"):
        return line.rstrip(), None
    if "=" not in content:
        return line.rstrip(), None

    candidate_strings = extract_quoted_strings(content)
    for candidate in candidate_strings:
        detected = detect_field_type(candidate)
        if detected is not None:
            annotated = f"{content}{comment} # suspicious:{detected}".rstrip()
            return annotated, detected
    return line.rstrip(), None


def annotate_text(raw: str) -> tuple[str, list[tuple[int, str]]]:
    annotated_lines: list[str] = []
    suspicious: list[tuple[int, str]] = []
    for index, line in enumerate(raw.splitlines(), start=1):
        annotated_line, detected = annotate_line(line)
        annotated_lines.append(annotated_line)
        if detected:
            suspicious.append((index, detected))
    return "\n".join(annotated_lines) + ("\n" if raw.endswith("\n") else ""), suspicious


def walk_values(value: Any) -> list[tuple[list[str], Any, str | None]]:
    results: list[tuple[list[str], Any, str | None]] = []
    if isinstance(value, str):
        results.append(([], value, detect_field_type(value)))
    elif isinstance(value, dict):
        for key, item in value.items():
            for path, leaf, detected in walk_values(item):
                results.append(([key] + path, leaf, detected))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            for path, leaf, detected in walk_values(item):
                results.append(([str(index)] + path, leaf, detected))
    return results


def mutate_value(value: Any, target_type: str) -> Any:
    if isinstance(value, str):
        if detect_field_type(value) is not None:
            return value
        return PLACEHOLDERS[target_type]
    if isinstance(value, dict):
        return {k: mutate_value(v, target_type) for k, v in value.items()}
    if isinstance(value, list):
        return [mutate_value(item, target_type) for item in value]
    if isinstance(value, tuple):
        return tuple(mutate_value(item, target_type) for item in value)
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
        pairs = ", ".join(f"{toml_key(k)} = {render_value(v)}" for k, v in value.items())
        return f"{{{pairs}}}"
    raise TypeError(f"Unsupported TOML value type: {type(value)}")


def dump_toml(obj: Any, top_level: bool = True) -> str:
    if isinstance(obj, dict):
        lines: list[str] = []
        for key, value in obj.items():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                for item in value:
                    lines.append(f"[[{key}]]")
                    for inner_key, inner_value in item.items():
                        lines.append(f"{toml_key(inner_key)} = {render_value(inner_value)}")
                    lines.append("")
            elif isinstance(value, dict):
                lines.append(f"[{key}]")
                for inner_key, inner_value in value.items():
                    lines.append(f"{toml_key(inner_key)} = {render_value(inner_value)}")
                lines.append("")
            else:
                lines.append(f"{toml_key(key)} = {render_value(value)}")
        return "\n".join(lines).rstrip() + "\n"
    return render_value(obj) + "\n"


def build_mutated_toml(parsed: dict[str, Any], target_type: str) -> str:
    mutated = mutate_value(parsed, target_type)
    return dump_toml(mutated)


def process_pipfile_file(pipfile_path: Path) -> dict[str, Any]:
    raw = read_file(pipfile_path)
    annotated_text, suspicious = annotate_text(raw)
    annotated_file = pipfile_path.with_name(pipfile_path.stem + "_annotated" + pipfile_path.suffix)
    write_file(annotated_file, annotated_text)

    report = {"file": str(pipfile_path), "suspicious": suspicious}

    try:
        parsed = toml_loads(raw)
    except Exception:
        report["parsed"] = False
        return report

    report["parsed"] = True
    for field_type in FIELD_TYPES:
        mutated_file = pipfile_path.with_name(f"{pipfile_path.stem}_{field_type.replace(' ', '_')}{pipfile_path.suffix}")
        mutated_toml = build_mutated_toml(parsed, field_type)
        write_file(mutated_file, mutated_toml)

    return report


def scan_pipfile_root(root_path: Path) -> list[dict[str, Any]]:
    root_path = root_path.resolve()
    results: list[dict[str, Any]] = []
    for name in ["Pipfile", "pipfile"]:
        for pipfile_path in sorted(root_path.rglob(name)):
            if pipfile_path.is_file():
                results.append(process_pipfile_file(pipfile_path))
    return results


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Scan Pipfile directories and mutate content with real placeholders.")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Root directory to scan for Pipfile files (default: current directory)",
    )
    args = parser.parse_args()

    root_path = Path(args.root)
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"Root directory not found: {root_path}")

    results = scan_pipfile_root(root_path)
    for result in results:
        print(f"File: {result['file']}")
        if result["suspicious"]:
            for line_no, field_type in result["suspicious"]:
                print(f"  line {line_no}: suspicious {field_type}")
        else:
            print("  no suspicious fields detected")
        if not result.get("parsed", False):
            print("  warning: failed to parse this Pipfile, only annotation file created")


if __name__ == "__main__":
    main()
