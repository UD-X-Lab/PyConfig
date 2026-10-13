#!/usr/bin/env python3
"""
Check whether non-git links (e.g., ftp) are reachable.

Reads URLs from data/links/setup/non_git_protocol_urls.txt (or a provided file)
and attempts to fetch them via curl (HEAD by default). Results are written to a
JSON report and optionally filtered into alive/dead lists.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_INPUT = Path("data/links/setup/non_git_protocol_urls.txt")
DEFAULT_OUTPUT = Path("data/links/setup/non_git_protocol_results.json")
DEFAULT_ALIVE = Path("data/links/setup/alive_non_git_urls.txt")
DEFAULT_DEAD = Path("data/links/setup/dead_non_git_urls.txt")


@dataclass
class CheckResult:
    url: str
    ok: bool
    status: Optional[int]
    error: Optional[str]

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "ok": self.ok,
            "status": self.status,
            "error": self.error,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify non-git URLs from a text file.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input file with URLs.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON report output file.")
    parser.add_argument("--alive-output", type=Path, default=DEFAULT_ALIVE, help="Write live URLs here.")
    parser.add_argument("--dead-output", type=Path, default=DEFAULT_DEAD, help="Write dead URLs here.")
    parser.add_argument("--timeout", type=int, default=15, help="Timeout (seconds) for each request.")
    parser.add_argument("--method", choices=["head", "get"], default="head", help="HTTP method to use.")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr.")
    return parser.parse_args()


def load_urls(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            url = raw.strip()
            if url and not url.startswith("#"):
                yield url


def check_url(url: str, method: str, timeout: int) -> CheckResult:
    curl_args = ["curl", "-LsS"]
    if method == "head":
        curl_args.extend(["-I"])
    curl_args.extend(["--max-time", str(timeout), url])

    print(curl_args)
    import pdb; pdb.set_trace()
    try:
        completed = subprocess.run(
            curl_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        return CheckResult(url, False, None, "curl executable not found")
    except Exception as exc:
        return CheckResult(url, False, None, f"curl error: {exc}")

    ok = completed.returncode == 0
    status = _extract_status_code(completed.stdout)
    error = None if ok else (completed.stderr.strip() or completed.stdout.strip() or f"curl return code {completed.returncode}")
    return CheckResult(url, ok, status, error)


def _extract_status_code(text: str) -> Optional[int]:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("HTTP/"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
    return None


def write_list(path: Path, urls: Iterable[str]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for url in urls:
            fh.write(url)
            fh.write("\n")


def main() -> None:
    args = parse_args()
    urls = list(load_urls(args.input))
    results = []

    for url in urls:
        if args.verbose:
            print(f"Checking {url}", file=sys.stderr)
        results.append(check_url(url, args.method, args.timeout))

    alive = [r.url for r in results if r.ok]
    dead = [r.url for r in results if not r.ok]

    args.output.write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")
    write_list(args.alive_output, alive)
    write_list(args.dead_output, dead)


if __name__ == "__main__":
    main()
