from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse


BASE_DIR = Path(__file__).parent
INPUT = BASE_DIR / "missing_package_urls_in_setup_fields.json"
OUTPUT = BASE_DIR / "missing_package_registry_urls_in_setup_fields.json"

# Known registry hosts. Expand this list as new registries are identified.
REGISTRY_DOMAINS = {
    "pypi.org",
    "pypi.python.org",
    "test.pypi.org",
    "files.pythonhosted.org",
    "pythonhosted.org",
}

# Registry indicators for mirrors or custom indices.
REGISTRY_SUFFIXES = (
    ".pypi.org",
)

REGISTRY_SUBSTRINGS = (
    "pypi",
    "pypicloud",
)


def extract_domain(url: str) -> Optional[str]:
    """Return the bare domain portion of a URL (lowercased), or None on failure."""
    candidate = url.strip()

    # Handle composite schemes like git+https://
    if "://" in candidate and "+" in candidate.split("://", 1)[0]:
        candidate = candidate.split("+", 1)[1]

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None

    if not parsed.netloc:
        return None

    host = parsed.netloc.split("@")[-1].split(":")[0].lower()
    return host or None


def is_registry_domain(domain: str) -> bool:
    domain = domain.lower()
    if domain in REGISTRY_DOMAINS:
        return True
    if any(domain.endswith(suffix) for suffix in REGISTRY_SUFFIXES):
        return True
    return any(token in domain for token in REGISTRY_SUBSTRINGS)


def iter_registry_urls(data: Iterable[dict]) -> Iterable[dict]:
    seen: set[tuple[str, str]] = set()
    for item in data:
        url = item.get("url")
        if not url:
            continue
        domain = extract_domain(url)
        if not domain or not is_registry_domain(domain):
            continue
        key = (url, domain)
        if key in seen:
            continue
        seen.add(key)
        yield {"url": url, "domain": domain}


def main() -> None:
    data = json.loads(INPUT.read_text())
    results = list(iter_registry_urls(data))
    OUTPUT.write_text(json.dumps(results, indent=2))
    print(f"Wrote {len(results)} registry URLs to {OUTPUT}")


if __name__ == "__main__":
    main()
