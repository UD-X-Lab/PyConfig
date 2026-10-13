#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TypeVar
from urllib import error, request
from urllib.parse import urlparse

T = TypeVar("T")

try:
    from tqdm import tqdm
except ModuleNotFoundError:  # pragma: no cover
    def tqdm(iterable: Iterable[T], *args, **kwargs) -> Iterable[T]:
        return iterable  # type: ignore[return-value]


SOURCE_FILES: List[Path] = [
    Path("data/links/github_hijack_account/pipfile/dead_urls_other.txt"),
    Path("data/links/github_hijack_account/pipfile/invalid_urls_other.txt"),
    Path("data/links/github_hijack_account/pyproject/dead_urls_other.txt"),
    Path("data/links/github_hijack_account/pyproject/invalid_urls_other.txt"),
    Path("data/links/github_hijack_account/requirements/dead_urls_other.txt"),
    Path("data/links/github_hijack_account/requirements/invalid_urls_other.txt"),
    Path("data/links/github_hijack_account/setup/dead_urls_other.txt"),
    Path("data/links/github_hijack_account/setup/invalid_urls_other.txt"),
]

OUTPUT_PATH = Path("data/links/github_hijack_account/package_url_report.json")

# Order matters: keep longer suffixes first so we do not match ".gz" ahead of ".tar.gz".
DIST_SUFFIXES = tuple(
    sorted(
        {
            ".tar.gz",
            ".tar.bz2",
            ".tar.xz",
            ".tar.zst",
            ".tar.lz",
            ".tar.lzma",
            ".tar",
            ".tgz",
            ".tbz2",
            ".txz",
            ".zip",
            ".whl",
            ".egg",
            ".bz2",
            ".gz",
            ".xz",
        },
        key=len,
        reverse=True,
    )
)

TRAILING_CHARS = "'\"`>);,."


def strip_fragment(url: str) -> str:
    return url.split("#", 1)[0].strip()


def clean_url(url: str) -> str:
    trimmed = strip_fragment(url)
    return trimmed.strip()


def sanitized_path(path: str) -> str:
    sanitized = path.rstrip("/")
    while sanitized and sanitized[-1] in TRAILING_CHARS:
        sanitized = sanitized[:-1]
    return sanitized


def is_distribution_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    path = sanitized_path(parsed.path.lower())
    return any(path.endswith(suffix) for suffix in DIST_SUFFIXES)


def domain_exists(domain: Optional[str], cache: Dict[str, Optional[bool]]) -> Optional[bool]:
    if not domain:
        return None
    if domain in cache:
        return cache[domain]

    try:
        socket.getaddrinfo(domain, None)
    except socket.gaierror:
        cache[domain] = False
    except Exception:
        cache[domain] = None
    else:
        cache[domain] = True

    return cache[domain]


def package_exists(url: str, domain_ok: Optional[bool], cache: Dict[str, Optional[bool]]) -> Optional[bool]:
    if domain_ok is False:
        return None
    if domain_ok is None:
        return None
    if url in cache:
        return cache[url]

    try:
        parsed = urlparse(url)
    except ValueError:
        cache[url] = None
        return cache[url]
    if parsed.scheme not in {"http", "https"}:
        cache[url] = None
        return cache[url]

    def try_request(method: str) -> Optional[int]:
        req = request.Request(
            url,
            headers={"User-Agent": "distribution-url-checker"},
            method=method,
        )
        try:
            with request.urlopen(req, timeout=8) as response:
                return response.status
        except error.HTTPError as http_err:
            return http_err.code
        except error.URLError:
            return None

    status = try_request("HEAD")
    if status == 405:
        status = try_request("GET")

    if status is None:
        cache[url] = None
    elif status == 404:
        cache[url] = False
    elif status >= 500:
        cache[url] = None
    else:
        cache[url] = True

    return cache[url]


def gather_distribution_urls() -> List[tuple[str, str]]:
    urls: List[tuple[str, str]] = []
    for path in SOURCE_FILES:
        if not path.exists():
            continue

        with path.open(encoding="utf-8") as handle:
            for line in handle:
                candidate = clean_url(line)
                if not candidate:
                    continue
                if not is_distribution_url(candidate):
                    continue
                urls.append((str(path), candidate))
    return urls


def main() -> None:
    domain_cache: Dict[str, Optional[bool]] = {}
    package_cache: Dict[str, Optional[bool]] = {}
    results: List[dict] = []

    for source_file, url in tqdm(gather_distribution_urls(), desc="Checking URLs"):
        parsed = urlparse(url)
        domain = parsed.hostname or parsed.netloc

        domain_ok = domain_exists(domain, domain_cache)
        package_ok = package_exists(url, domain_ok, package_cache)

        results.append(
            {
                "source_file": source_file,
                "original_url": url,
                "domain": domain,
                "domain_exists": domain_ok,
                "package_exists": package_ok,
            }
        )

    OUTPUT_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
