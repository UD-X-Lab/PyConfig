#!/usr/bin/env python3
"""
Check URLs against the VirusTotal API to flag potential malicious entries.

Usage (from project root):
    python3 data/links/virustotal_scan.py \
        --api-key YOUR_API_KEY \
        --json-output data/links/domain_takeover/virustotal_report.json \
        --text-output data/links/domain_takeover/virustotal_malicious.txt
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

try:
    import requests
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "The 'requests' package is required to run this script. Install it via pip."
    ) from exc

DEFAULT_INPUTS = (
    Path("data/links/pipfile/alive_urls.txt"),
    Path("data/links/setup/alive_urls.txt"),
    Path("data/links/pyproject/alive_urls.txt"),
    Path("data/links/requirements/alive_urls.txt"),
)

DEFAULT_JSON_OUTPUT = Path("data/links/domain_takeover/virustotal_report.json")
DEFAULT_TEXT_OUTPUT = Path("data/links/domain_takeover/virustotal_malicious.txt")
DEFAULT_CACHE_FILE = Path("data/links/domain_takeover/virustotal_cache.json")

VT_URL_TEMPLATE = "https://www.virustotal.com/api/v3/urls/{url_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query VirusTotal for URL verdicts.")
    parser.add_argument(
        "--inputs",
        nargs="*",
        type=Path,
        default=list(DEFAULT_INPUTS),
        help="Input files containing URLs (one per line).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="VirusTotal API key (falls back to VT_API_KEY environment variable).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=16.0,
        help="Seconds to sleep between requests (free tier requires >= 15s).",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help="JSON report output path.",
    )
    parser.add_argument(
        "--text-output",
        type=Path,
        default=DEFAULT_TEXT_OUTPUT,
        help="Text file containing URLs flagged as malicious/suspicious.",
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=DEFAULT_CACHE_FILE,
        help="JSON cache file storing previously scanned URLs (default: data/links/domain_takeover/virustotal_cache.json).",
    )
    return parser.parse_args()


def load_urls(paths: Iterable[Path]) -> List[str]:
    urls: Set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                url = raw.strip()
                if url and not url.startswith("#"):
                    urls.add(url)
    return sorted(urls)


def load_cache(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(path: Path, cache: Dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def vt_url_id(url: str) -> str:
    """Encode a URL into the format required by the VT v3 API."""
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8")
    return encoded.strip("=")


def fetch_vt_record(session: requests.Session, api_key: str, url: str) -> Optional[dict]:
    """Fetch the latest VirusTotal analysis for the given URL."""
    headers = {"x-apikey": api_key}
    response = session.get(VT_URL_TEMPLATE.format(url_id=vt_url_id(url)), headers=headers, timeout=30)
    if response.status_code == 404:
        # No existing analysis
        return None
    response.raise_for_status()
    return response.json()


def extract_stats(record: dict) -> Dict[str, int]:
    data = record.get("data", {})
    attributes = data.get("attributes", {})
    stats = attributes.get("last_analysis_stats", {})
    return {k: int(v) for k, v in stats.items()}


def main() -> None:
    args = parse_args()
    api_key = args.api_key or os.getenv("VT_API_KEY")
    if not api_key:
        raise SystemExit("VirusTotal API key not provided. Use --api-key or set VT_API_KEY.")

    urls = load_urls(args.inputs)
    session = requests.Session()
    cache: Dict[str, dict] = load_cache(args.cache_file)
    results: List[dict] = []
    malicious_urls: List[str] = []

    for index, url in enumerate(urls, start=1):
        print(f"[{index}/{len(urls)}] Querying VirusTotal for {url}")
        if url in cache and cache[url]:
            record = cache[url]
            print("  cached result found, skipping API call.")
        else:
            try:
                record = fetch_vt_record(session, api_key, url)
            except requests.HTTPError as exc:
                print(f"  HTTP error for {url}: {exc}")
                record = None
            except requests.RequestException as exc:
                print(f"  Request failed for {url}: {exc}")
                record = None

            cache[url] = record
            if index < len(urls):
                time.sleep(args.delay)

        stats = extract_stats(record) if record else {}
        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        verdict = "unknown"
        if record is None:
            verdict = "no-data"
        elif malicious > 0:
            verdict = "malicious"
        elif suspicious > 0:
            verdict = "suspicious"
        else:
            verdict = "clean"

        results.append(
            {
                "url": url,
                "verdict": verdict,
                "stats": stats,
            }
        )
        if verdict in {"malicious", "suspicious"}:
            malicious_urls.append(url)

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    args.text_output.write_text("\n".join(malicious_urls), encoding="utf-8")

    save_cache(args.cache_file, cache)

    print(f"Completed scanning {len(urls)} URLs.")
    print(f"Malicious/suspicious URLs: {len(malicious_urls)}")
    print(f"JSON report written to: {args.json_output}")
    print(f"Text list written to: {args.text_output}")


if __name__ == "__main__":
    main()
