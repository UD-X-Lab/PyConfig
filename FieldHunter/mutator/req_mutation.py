import re
from pathlib import Path

FIELD_TYPES = ["url", "class", "function", "shell command", "script file"]

URL_PATTERNS = re.compile(
    r"^(?:https?://|git\+|ssh://|ftp://|file://|svn\+|hg\+|bzr\+|git@|https?:\\\\|\\./|\\../).+",
    re.IGNORECASE,
)
SCRIPT_EXTENSIONS = {"py", "sh", "bat", "cmd", "ps1", "pl", "rb"}


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
    if any(token in value for token in ["&&", "||", "|", ";", "$()", "`", "script", "bash", "sh", "python -c", "cmd", "powershell"]):
        return True
    return False


def is_class_reference(value: str) -> bool:
    if "." not in value:
        return False
    value = value.strip().split("#", 1)[0].strip()
    last = value.rsplit(".", 1)[-1]
    return bool(last) and last[0].isupper()


def is_function_reference(value: str) -> bool:
    if value.strip().endswith(")") or value.strip().endswith("("):
        return True
    if "." in value:
        last = value.strip().split(".", 1)[-1]
        return bool(last) and last[0].islower() and not value.strip().startswith("-")
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


def build_placeholder(field_type: str) -> str:
    return {
        "url": "https://github.com/mhammond/pywin32/archive/refs/tags/b306.tar.gz#egg=pywin32",
        "class": "FieldHunter.mutator.real_types.ExampleClass",
        "function": "FieldHunter.mutator.real_types.example_function",
        "shell command": "bash -lc \"echo real_shell_command\"",
        "script file": "FieldHunter/mutator/real_script.py",
    }[field_type]


def mutate_line(line: str, target_type: str) -> str:
    content, comment = split_line_comment(line)
    if not content.strip() or content.lstrip().startswith("#") or content.strip().startswith("-"):
        return line.rstrip()
    detected = detect_field_type(content)
    if detected is not None:
        return line.rstrip()
    placeholder = build_placeholder(target_type)
    return f"{placeholder}{comment}".rstrip()


def annotate_line(line: str) -> tuple[str, str | None]:
    content, comment = split_line_comment(line)
    if not content.strip() or content.lstrip().startswith("#") or content.strip().startswith("-"):
        return line.rstrip(), None
    detected = detect_field_type(content)
    if detected is None:
        return line.rstrip(), None
    annotated = f"{content}{comment} # suspicious:{detected}".rstrip()
    return annotated, detected


def process_requirements_file(requirements_path: Path) -> dict[str, list[tuple[int, str]]]:
    text = read_file(requirements_path)
    lines = text.splitlines()
    annotated_lines: list[str] = []
    suspicious_report: list[tuple[int, str]] = []

    mutations: dict[str, list[str]] = {
        "url": [],
        "class": [],
        "function": [],
        "shell command": [],
        "script file": [],
    }

    for index, line in enumerate(lines, start=1):
        annotated_line, detected = annotate_line(line)
        annotated_lines.append(annotated_line)
        if detected:
            suspicious_report.append((index, detected))

        for field_type in mutations:
            mutations[field_type].append(mutate_line(line, field_type))

    annotated_file = requirements_path.with_name(requirements_path.stem + "_annotated" + requirements_path.suffix)
    write_file(annotated_file, "\n".join(annotated_lines) + ("\n" if lines else ""))

    for field_type, mutated_lines in mutations.items():
        mutated_file = requirements_path.with_name(f"{requirements_path.stem}_{field_type.replace(' ', '_')}{requirements_path.suffix}")
        write_file(mutated_file, "\n".join(mutated_lines) + ("\n" if lines else ""))

    return {"file": str(requirements_path), "suspicious": suspicious_report}


def scan_requirements_root(root_path: Path) -> list[dict[str, list[tuple[int, str]]]]:
    root_path = root_path.resolve()
    results: list[dict[str, list[tuple[int, str]]]] = []
    for requirements_path in sorted(root_path.rglob("requirements.txt")):
        if requirements_path.is_file():
            results.append(process_requirements_file(requirements_path))
    return results


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Scan requirements directories and mutate non-suspicious fields.")
    parser.add_argument(
        "root",
        nargs="?",
        default="requirements",
        help="Root directory to scan for requirements.txt files (default: requirements)",
    )
    args = parser.parse_args()

    root_path = Path(args.root)
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"Root directory not found: {root_path}")

    results = scan_requirements_root(root_path)
    for result in results:
        if result["suspicious"]:
            print(f"File: {result['file']}")
            for line_no, field_type in result["suspicious"]:
                print(f"  line {line_no}: suspicious {field_type}")
        else:
            print(f"File: {result['file']} - no suspicious fields detected")


if __name__ == "__main__":
    main()
