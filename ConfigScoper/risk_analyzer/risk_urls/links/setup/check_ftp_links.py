#!/usr/bin/env python3
"""
Check whether FTP links listed in a file are reachable.

The script attempts an anonymous FTP connection (or uses credentials from the URL),
optionally navigates to the requested path, and reports whether the connection/file
appears accessible.
"""

from __future__ import annotations

import argparse
import ftplib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse

DEFAULT_INPUT = Path("data/links/setup/non_git_protocol_urls.txt")
DEFAULT_OUTPUT = Path("data/links/setup/ftp_check_results.json")
DEFAULT_ALIVE_OUTPUT = Path("data/links/setup/alive_ftp_urls.txt")
DEFAULT_DEAD_OUTPUT = Path("data/links/setup/dead_ftp_urls.txt")


@dataclass
class CheckResult:
    url: str
    ok: bool
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {"url": self.url, "ok": self.ok, "error": self.error}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify FTP URLs from a file.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="File containing candidate URLs.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to JSON results file.")
    parser.add_argument("--alive-output", type=Path, default=DEFAULT_ALIVE_OUTPUT, help="File to list reachable FTP URLs.")
    parser.add_argument("--dead-output", type=Path, default=DEFAULT_DEAD_OUTPUT, help="File to list unreachable FTP URLs.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Connection timeout in seconds.")
    parser.add_argument("--verbose", action="store_true", help="Print progress information to stderr.")
    return parser.parse_args()


def load_ftp_urls(path: Path) -> list[str]:
    urls: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            url = raw.strip()
            if url and url.lower().startswith("ftp://"):
                urls.append(url)
    return urls


def split_path(path: str) -> tuple[str, Optional[str]]:
    if not path or path == "/":
        return "", None
    directory, _, filename = path.rstrip("/").rpartition("/")
    if not filename and directory:
        filename, directory = directory, ""
    return unquote(directory), unquote(filename) if filename else None


def check_ftp(url: str, timeout: float) -> CheckResult:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return CheckResult(url, False, "missing host in URL")

    port = parsed.port or 21
    user = parsed.username or "anonymous"
    password = parsed.password or "anonymous@"
    directory, filename = split_path(parsed.path or "")

    ftp = ftplib.FTP()
    try:
        ftp.connect(host, port, timeout=timeout)
        ftp.login(user, password)

        if directory:
            ftp.cwd(directory)

        if filename:
            # Try to get file size to confirm presence (fails gracefully on permission issues)
            try:
                ftp.size(filename)
            except ftplib.error_perm:
                # Fall back to listing directory to infer existence
                contents = ftp.nlst()
                if filename not in contents:
                    raise

        ftp.quit()
        return CheckResult(url, True, None)
    except ftplib.all_errors as exc:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
        return CheckResult(url, False, str(exc))
    except OSError as exc:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
        return CheckResult(url, False, str(exc))


def write_list(path: Path, items: Iterable[str]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(item)
            fh.write(os.linesep)


def main() -> None:
    args = parse_args()
    urls = load_ftp_urls(args.input)
    results = [check_ftp(url, args.timeout) for url in urls]

    alive = [r.url for r in results if r.ok]
    dead = [r.url for r in results if not r.ok]

    args.output.write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")
    write_list(args.alive_output, alive)
    write_list(args.dead_output, dead)


if __name__ == "__main__":
    main()
