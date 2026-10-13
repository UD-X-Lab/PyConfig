from __future__ import annotations

"""
Find expired domains inside pipfile_stats.json -> files -> fields values.

Inputs:
- domains: data/links/expired_domain/expired_domains_dedup.json (key "domains")
- pipfile data: data/links/github_hijack_account/pipfile/pipfile_stats.json

Outputs:
- data/links/github_hijack_account/pipfile/expired_domain_field_matches.json
    list of {file, field, domain, urls}
- data/links/github_hijack_account/pipfile/expired_domain_field_matches_by_field.json
    {field: {"count": n, "items": [...]}}
"""

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

PIPFILE_STATS = Path("data/links/github_hijack_account/pipfile/pipfile_stats.json")
DOMAINS_PATH = Path("data/links/expired_domain/expired_domains_dedup.json")
OUTPUT_MATCHES = Path(
    "data/links/github_hijack_account/pipfile/expired_domain_field_matches.json"
)
OUTPUT_BY_FIELD = Path(
    "data/links/github_hijack_account/pipfile/expired_domain_field_matches_by_field.json"
)


def load_domains(path: Path) -> Tuple[str, ...]:
    data = json.loads(path.read_text())
    domains = data.get("domains", []) if isinstance(data, dict) else []
    return tuple(d.strip().lower() for d in domains if d and str(d).strip())


def load_pipfile_files(path: Path) -> Dict:
    data = json.loads(path.read_text())
    return data.get("files", {})


def collect_matches(
    files: Dict[str, Dict],
    domains: Tuple[str, ...],
    patterns: Dict[str, re.Pattern],
) -> List[Dict]:
    results: List[Dict] = []
    for file_path, payload in files.items():
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


def group_by_field(results: List[Dict]) -> Dict[str, Dict[str, object]]:
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
    return grouped


def main() -> None:
    domains = load_domains(DOMAINS_PATH)
    patterns = {
        d: re.compile(r'[^\\s"\\\']*' + re.escape(d) + r'[^\\s"\\\']*', re.IGNORECASE)
        for d in domains
    }
    files = load_pipfile_files(PIPFILE_STATS)
    results = collect_matches(files, domains, patterns)
    grouped = group_by_field(results)

    OUTPUT_MATCHES.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MATCHES.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    OUTPUT_BY_FIELD.write_text(json.dumps(grouped, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
