from __future__ import annotations

"""
Scan data/links/domain_takeover/pyproject/files.json for fields that mention any
domain listed in data/links/domain_takeover/takeover_domains. For each match,
record the file path, field key, matched domain, and the surrounding token
(treated as the URL/segment containing the domain). Output is written to
data/links/domain_takeover/pyproject/domain_field_matches.json.
"""

import json
import re
from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple


BASE = Path("data/links/domain_takeover")
FILES_JSON = BASE / "pyproject" / "files.json"
TAKEOVER_DOMAINS = BASE / "takeover_domains"
OUTPUT = BASE / "pyproject" / "domain_field_matches.json"
OUTPUT_BY_FIELD = BASE / "pyproject" / "domain_field_matches_by_field.json"
SETUP_FILES_JSON = BASE / "setup" / "setup_files.json"
SETUP_OUTPUT = BASE / "setup" / "domain_field_matches.json"
SETUP_OUTPUT_BY_FIELD = BASE / "setup" / "domain_field_matches_by_field.json"

CHUNK_SIZE = 1 << 16  # 64KB


def load_domains(path: Path) -> Tuple[str, ...]:
    return tuple(
        d.strip().lower()
        for d in path.read_text().splitlines()
        if d.strip()
    )


def iter_files_entries(path: Path) -> Iterator[Tuple[str, Dict]]:
    """
    Stream the top-level entries under the \"files\" object without loading
    the whole JSON into memory. Each yielded item is (file_path, file_payload).
    """
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as f:
        buffer = ""
        pos = 0

        def fill(min_needed: int = 1) -> bool:
            nonlocal buffer
            while len(buffer) - pos < min_needed:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    return False
                buffer += chunk
            return True

        # Seek to the start of the \"files\" object (the '{' after \"files\":)
        while True:
            if not fill():
                raise RuntimeError('Could not find "files" object.')
            idx = buffer.find('"files"', pos)
            if idx == -1:
                pos = len(buffer)
                continue
            brace_idx = buffer.find("{", idx)
            if brace_idx != -1:
                pos = brace_idx
                break
            pos = len(buffer)

        if not fill():
            raise RuntimeError("Unexpected EOF seeking start of files object.")
        if buffer[pos] != "{":
            raise RuntimeError("Malformed files object start.")
        pos += 1  # enter the files object

        while True:
            # Skip whitespace and commas
            while True:
                if pos >= len(buffer) and not fill():
                    return
                if pos < len(buffer) and buffer[pos] in " \r\n\t,":
                    pos += 1
                    continue
                break

            if not fill():
                return
            if buffer[pos] == "}":  # end of files object
                return

            # Parse key (file path string)
            key = parse_value(decoder, f, buffer, pos)
            pos += key[1]
            buffer = key[2]
            file_path = key[0]

            # Skip whitespace
            while True:
                if pos >= len(buffer) and not fill():
                    return
                if pos < len(buffer) and buffer[pos] in " \r\n\t":
                    pos += 1
                    continue
                break

            # Expect colon
            if pos >= len(buffer) and not fill():
                return
            if buffer[pos] != ":":
                raise RuntimeError("Expected ':' after key in files object.")
            pos += 1

            # Skip whitespace
            while True:
                if pos >= len(buffer) and not fill():
                    return
                if pos < len(buffer) and buffer[pos] in " \r\n\t":
                    pos += 1
                    continue
                break

            # Parse value (file payload object)
            val = parse_value(decoder, f, buffer, pos)
            pos += val[1]
            buffer = val[2]
            payload = val[0]

            yield file_path, payload

            # Compact buffer occasionally to avoid unbounded growth
            if pos > CHUNK_SIZE:
                buffer = buffer[pos:]
                pos = 0


def iter_setup_entries(path: Path) -> Iterator[Tuple[str, Dict]]:
    """Iterate setup_files.json entries (fits in memory, ~62MB)."""
    data = json.loads(path.read_text())
    for file_path, payload in data.items():
        yield file_path, payload


def parse_value(
    decoder: json.JSONDecoder, f, buffer: str, pos: int
) -> Tuple[object, int, str]:
    """
    Parse a JSON value starting at buffer[pos:], reading more chunks if needed.
    Returns (value, length_consumed, updated_buffer).
    """
    while True:
        try:
            obj, end = decoder.raw_decode(buffer[pos:])
            return obj, end, buffer
        except json.JSONDecodeError:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                raise
            buffer += chunk


def extract_matches() -> None:
    domains = load_domains(TAKEOVER_DOMAINS)
    patterns = {
        d: re.compile(r'[^\\s"\\\']*' + re.escape(d) + r'[^\\s"\\\']*', re.IGNORECASE)
        for d in domains
    }

    # pyproject
    pyproject_results = collect_matches(iter_files_entries(FILES_JSON), domains, patterns)
    write_outputs(pyproject_results, OUTPUT, OUTPUT_BY_FIELD)

    # setup
    setup_results = collect_matches(iter_setup_entries(SETUP_FILES_JSON), domains, patterns)
    write_outputs(setup_results, SETUP_OUTPUT, SETUP_OUTPUT_BY_FIELD)


def collect_matches(
    entries: Iterator[Tuple[str, Dict]],
    domains: Tuple[str, ...],
    patterns: Dict[str, re.Pattern],
) -> list:
    results = []
    for file_path, payload in entries:
        fields: Dict = payload.get("fields", {}) if isinstance(payload, dict) else {}
        if not fields:
            continue
        for field_key, field_value in fields.items():
            try:
                text = json.dumps(field_value, ensure_ascii=False)
            except Exception:
                continue
            lower_text = text.lower()
            for domain in domains:
                if domain not in lower_text:
                    continue
                urls = sorted(
                    {m.group(0) for m in patterns[domain].finditer(text)}
                )
                if urls:
                    results.append(
                        {
                            "file": file_path,
                            "field": field_key,
                            "domain": domain,
                            "urls": urls,
                        }
                    )
    return results


def write_outputs(results, matches_path: Path, grouped_path: Path) -> None:
    matches_path.parent.mkdir(parents=True, exist_ok=True)
    with matches_path.open("w", encoding="utf-8") as out:
        json.dump(results, out, ensure_ascii=False, indent=2)

    grouped: Dict[str, Dict[str, object]] = {}
    for item in results:
        field = item["field"]
        bucket = grouped.setdefault(field, {"count": 0, "items": []})
        bucket["items"].append(
            {
                "file": item["file"],
                "domain": item["domain"],
                "urls": item["urls"],
            }
        )
        bucket["count"] += 1

    with grouped_path.open("w", encoding="utf-8") as out:
        json.dump(grouped, out, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    extract_matches()
