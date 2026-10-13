from __future__ import annotations

"""
Find URLs in requirements_link_sources.json that contain any expired domain.
Sources:
- Domains: data/links/expired_domain/expired_domains_dedup.json (key: "domains")
- URLs: data/links/github_hijack_account/requirements/map/requirements_link_sources.json

Outputs:
- data/links/github_hijack_account/requirements/map/expired_domain_urls.json
    [
      {"domain": "<domain>", "count": <url_count>, "urls": ["..."]}
    ]
"""

import json
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

DOMAINS_PATH = Path("data/links/expired_domain/expired_domains_dedup.json")
LINK_SOURCES_PATH = Path(
    "data/links/github_hijack_account/requirements/map/requirements_link_sources.json"
)
OUTPUT_PATH = Path(
    "data/links/github_hijack_account/requirements/map/expired_domain_urls.json"
)


def load_domains(path: Path) -> Tuple[str, ...]:
    data = json.loads(path.read_text())
    domains = data.get("domains", []) if isinstance(data, dict) else []
    return tuple(d.strip().lower() for d in domains if d and str(d).strip())


def load_urls(path: Path) -> Iterable[str]:
    data = json.loads(path.read_text())
    for section in data.values():
        for url in section.keys():
            yield url.lower()


def collect_matches(domains: Iterable[str], urls: Iterable[str]) -> List[Dict]:
    hits: Dict[str, Set[str]] = {d: set() for d in domains}
    for url in urls:
        for domain in domains:
            if domain in url:
                hits[domain].add(url)
    results = []
    for domain, url_set in hits.items():
        if url_set:
            sorted_urls = sorted(url_set)
            results.append(
                {"domain": domain, "count": len(sorted_urls), "urls": sorted_urls}
            )
    return results


def main() -> None:
    domains = load_domains(DOMAINS_PATH)
    urls = load_urls(LINK_SOURCES_PATH)
    results = collect_matches(domains, urls)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
