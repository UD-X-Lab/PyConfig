from __future__ import annotations

"""
Match expired domains against setup_files.json and summarize hits by field.
- Domains source: data/links/expired_domain/expired_domains_dedup.json (key: "domains")
- Search target: data/links/domain_takeover/setup/setup_files.json
- Outputs:
    * data/links/domain_takeover/setup/expired_domain_field_matches.json
    * data/links/domain_takeover/setup/expired_domain_field_matches_by_field.json
"""

import json
import re
from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple

BASE = Path("data/links/domain_takeover")
SETUP_FILES_JSON = BASE / "setup" / "setup_files.json"
EXPIRED_DOMAINS_JSON = Path("data/links/expired_domain/expired_domains_dedup.json")
OUTPUT = BASE / "setup" / "expired_domain_field_matches.json"
OUTPUT_BY_FIELD = BASE / "setup" / "expired_domain_field_matches_by_field.json"


def load_domains(path: Path) -> Tuple[str, ...]:
    data = json.loads(path.read_text())
    domains = data.get("domains", []) if isinstance(data, dict) else []
    return tuple(d.strip().lower() for d in domains if d and str(d).strip())


def iter_setup_entries(path: Path) -> Iterator[Tuple[str, Dict]]:
    """Iterate setup_files.json entries (fits in memory, ~62MB)."""
    data = json.loads(path.read_text())
    for file_path, payload in data.items():
        yield file_path, payload


def collect_matches(
    entries: Iterable[Tuple[str, Dict]],
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
                urls = sorted({m.group(0) for m in patterns[domain].finditer(text)})
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


def main() -> None:
    domains = load_domains(EXPIRED_DOMAINS_JSON)
    patterns = {
        d: re.compile(r'[^\\s"\\\']*' + re.escape(d) + r'[^\\s"\\\']*', re.IGNORECASE)
        for d in domains
    }
    results = collect_matches(
        iter_setup_entries(SETUP_FILES_JSON),
        domains,
        patterns,
    )
    write_outputs(results, OUTPUT, OUTPUT_BY_FIELD)


if __name__ == "__main__":
    main()
