#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TypeVar, Callable
from urllib import error, request
from urllib.parse import urlparse

T = TypeVar("T")

try:
    from tqdm import tqdm
except ModuleNotFoundError:  # pragma: no cover
    def tqdm(iterable: Iterable[T], *args, **kwargs) -> Iterable[T]:
        return iterable  # type: ignore[return-value]


SOURCE_FILES: List[Path] = [
    Path("data/links/github_hijack_account/pipfile/dead_urls_github.txt"),
    Path("data/links/github_hijack_account/pipfile/invalid_urls_github.txt"),
    Path("data/links/github_hijack_account/pyproject/dead_urls_github.txt"),
    Path("data/links/github_hijack_account/pyproject/invalid_urls_github.txt"),
    Path("data/links/github_hijack_account/requirements/dead_urls_github.txt"),
    Path("data/links/github_hijack_account/requirements/invalid_urls_github.txt"),
    Path("data/links/github_hijack_account/setup/dead_urls_github.txt"),
    Path("data/links/github_hijack_account/setup/invalid_urls_github.txt"),
]

OUTPUT_PATH = Path("data/links/github_hijack_account/github_url_report.json")

VCS_PREFIX_PATTERN = re.compile(r"^(?P<vcs>[a-z0-9]+)\+(?P<body>.+)$", flags=re.IGNORECASE)


def strip_fragment(url: str) -> str:
    return url.split("#", 1)[0].strip()


def build_https_from_rest(rest: str) -> str:
    """Convert host/path portions that may still contain git@ or colon separators."""
    cleaned = rest.strip().lstrip("/")
    if cleaned.startswith("git@"):
        cleaned = cleaned.split("@", 1)[1]

    if cleaned.startswith("github.com:"):
        cleaned = cleaned.replace("github.com:", "github.com/", 1)
    elif cleaned.startswith("github.com;"):
        cleaned = cleaned.replace("github.com;", "github.com/", 1)

    if cleaned.startswith("github.com"):
        cleaned = cleaned[len("github.com") :].lstrip("/")
        host = "github.com"
    else:
        host = cleaned.split("/", 1)[0]
        cleaned = cleaned[len(host) :].lstrip("/")
        if host != "github.com":
            return f"https://{host}{('/' + cleaned) if cleaned else ''}"

    return f"https://{host}{('/' + cleaned) if cleaned else '/'}"


def normalize_url(raw_url: str) -> str:
    url = strip_fragment(raw_url)
    if not url:
        return ""

    match = VCS_PREFIX_PATTERN.match(url)
    body = match.group("body") if match else url

    normalized = body
    lower_body = body.lower()

    if lower_body.startswith(("https://", "http://")):
        normalized = body
    elif lower_body.startswith(("git://", "ssh://")):
        _, rest = body.split("://", 1)
        normalized = build_https_from_rest(rest)
    elif lower_body.startswith("git@github.com"):
        normalized = build_https_from_rest(body)
    elif lower_body.startswith("github.com"):
        normalized = build_https_from_rest(body)
    else:
        normalized = body

    # Handle git+https or git+http cases.
    if match:
        scheme_part = body.split("://", 1)[0].lower() if "://" in body else ""
        if scheme_part in {"https", "http"}:
            normalized = body
        elif scheme_part in {"git", "ssh"}:
            rest = body.split("://", 1)[1] if "://" in body else body
            normalized = build_https_from_rest(rest)

    normalized = normalized.strip()

    # Final cleanup for lingering git@ forms.
    if normalized.lower().startswith("https://git@github.com"):
        normalized = build_https_from_rest(normalized[len("https://") :])
    if normalized.lower().startswith("http://git@github.com"):
        normalized = build_https_from_rest(normalized[len("http://") :])

    if normalized.lower().startswith("git://github.com"):
        normalized = build_https_from_rest(normalized[len("git://") :])
    if normalized.lower().startswith("ssh://git@github.com"):
        normalized = build_https_from_rest(normalized[len("ssh://") :])

    # Ensure we prefer https for GitHub.
    parsed = urlparse(normalized)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower().endswith("github.com"):
        normalized_path = parsed.path if parsed.path else "/"
        normalized = f"https://github.com{normalized_path}"
        if parsed.query:
            normalized += f"?{parsed.query}"

    return normalized


def extract_author(normalized_url: str) -> Optional[str]:
    parsed = urlparse(normalized_url)
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [segment for segment in parsed.path.split("/") if segment]
    return parts[0] if parts else None


def author_exists(author: Optional[str], cache: Dict[str, Optional[bool]]) -> Optional[bool]:
    if not author:
        return None
    if author in cache:
        return cache[author]

    profile_url = f"https://github.com/{author}"
    req = request.Request(profile_url, headers={"User-Agent": "github-url-checker"})

    try:
        with request.urlopen(req, timeout=5) as response:
            cache[author] = response.status == 200
    except error.HTTPError as http_err:
        if http_err.code == 404:
            cache[author] = False
        else:
            cache[author] = None
    except error.URLError:
        cache[author] = None

    return cache[author]


def iter_github_lines(path: Path) -> Iterable[str]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped and "github" in stripped.lower():
                yield stripped


def process_file(path: Path, cache: Dict[str, Optional[bool]]) -> List[dict]:
    results: List[dict] = []
    if not path.exists():
        return results

    for original in iter_github_lines(path):
        normalized = normalize_url(original)
        author = extract_author(normalized)
        exists = author_exists(author, cache)

        results.append(
            {
                "source_file": str(path),
                "original_url": original,
                "normalized_url": normalized or None,
                "author": author,
                "author_exists": exists,
            }
        )

    return results


def main() -> None:
    cache: Dict[str, Optional[bool]] = {}
    all_results: List[dict] = []

    for source_file in tqdm(SOURCE_FILES, desc="Processing files"):
        for record in tqdm(
            process_file(source_file, cache),
            desc=f"URLs in {source_file.name}",
            leave=False,
        ):
            all_results.append(record)

    OUTPUT_PATH.write_text(json.dumps(all_results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
