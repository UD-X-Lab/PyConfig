#!/usr/bin/env python3
"""
Verify reachability of git SSH remotes pulled from pyproject invalid URLs.

This script reads `clean_invalid_urls.txt`, filters entries that look like
`ssh://...` or `git+ssh://...`, normalises them, and probes them via
`git ls-remote`. Results are written to JSON alongside convenience text files.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse, unquote

DEFAULT_INPUT = Path("data/links/pyproject/clean_invalid_urls.txt")
DEFAULT_RESULTS = Path("data/links/pyproject/git_ssh_check_results.json")
DEFAULT_ALIVE = Path("data/links/pyproject/alive_git_ssh_urls.txt")
DEFAULT_DEAD = Path("data/links/pyproject/dead_git_ssh_urls.txt")


@dataclass
class CheckResult:
    raw: str
    normalized: Optional[str]
    remote: Optional[str]
    revision: Optional[str]
    ok: bool
    returncode: Optional[int]
    error: Optional[str]

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "remote": self.remote,
            "revision": self.revision,
            "ok": self.ok,
            "returncode": self.returncode,
            "error": self.error,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check git SSH URLs harvested from pyproject invalid list.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Source text file.")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS, help="JSON output with full results.")
    parser.add_argument("--alive-output", type=Path, default=DEFAULT_ALIVE, help="File listing accessible remotes.")
    parser.add_argument("--dead-output", type=Path, default=DEFAULT_DEAD, help="File listing inaccessible remotes.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Timeout per git ls-remote call.")
    parser.add_argument("--keep-revision", action="store_true", help="Include revision when probing.")
    return parser.parse_args()


def load_candidates(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("ssh://") or line.startswith("git+ssh://"):
                yield line


def normalise_git_ssh(raw: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Return (remote, revision, normalized_url) for git ssh style entries.
    """
    if raw.startswith("git+ssh://"):
        body = raw[len("git+") :]
    elif raw.startswith("ssh://"):
        body = raw
    else:
        return None, None, None

    # Strip fragment (e.g., #egg=)
    main, hash_sep, frag = body.partition("#")

    # Some urls may contain template braces; leave them as-is but avoid parsing errors.
    parsed = urlparse(main)
    if not parsed.scheme or not parsed.netloc:
        return main, None, raw

    path = parsed.path or ""
    revision = None
    if "@" in path and path.count("@") == 1:
        prefix, _, rev = path.partition("@")
        # Only treat as revision if @ occurs after last '/'
        if prefix.rfind("/") < len(prefix) and rev:
            path = prefix
            revision = unquote(rev)

    remote = parsed._replace(path=path).geturl()
    normalized = f"git+{remote}" if not raw.startswith("git+") else f"git+{remote}"
    if hash_sep:
        normalized = f"{normalized}#{frag}"

    return remote, revision, normalized


def run_git_ls_remote(
    remote: str,
    revision: Optional[str],
    timeout: float,
    include_revision: bool,
) -> Tuple[bool, Optional[int], Optional[str]]:
    args = ["git", "ls-remote", "--exit-code", remote]
    if include_revision and revision:
        args.append(revision)

    env = os.environ.copy()
    ssh_command = env.get("GIT_SSH_COMMAND", "ssh")
    if "-o BatchMode" not in ssh_command:
        ssh_command = f"{ssh_command} -o BatchMode=yes"
    env["GIT_SSH_COMMAND"] = ssh_command

    try:
        completed = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env=env,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return False, None, f"timeout after {timeout:.1f}s"
    except FileNotFoundError:
        return False, None, "git executable not found"

    if completed.returncode == 0:
        return True, 0, None

    error_message = (completed.stderr or completed.stdout or "").strip()
    return False, completed.returncode, error_message or "unknown git error"


def write_list(path: Path, items: Iterable[str]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(item)
            fh.write("\n")


def main() -> None:
    args = parse_args()
    results: list[CheckResult] = []

    for raw in load_candidates(args.input):
        remote, revision, normalized = normalise_git_ssh(raw)
        if not remote:
            results.append(CheckResult(raw, normalized, remote, revision, False, None, "unable to parse git ssh url"))
            continue

        ok, rc, err = run_git_ls_remote(remote, revision, args.timeout, args.keep_revision)
        results.append(CheckResult(raw, normalized, remote, revision if args.keep_revision else None, ok, rc, err))

    args.results.write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")

    alive = [r.normalized or r.raw for r in results if r.ok]
    dead = [r.normalized or r.raw for r in results if not r.ok]
    write_list(args.alive_output, alive)
    write_list(args.dead_output, dead)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
