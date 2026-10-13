#!/usr/bin/env python3
"""
Check whether git+ssh VCS links listed in a file are reachable.

For each entry in `git_ssh_protocol_urls.txt`, the script normalises the remote URL,
optionally extracts the requested revision, and runs `git ls-remote` to verify access.
Results are written to JSON plus helper files listing alive/dead links.
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

DEFAULT_INPUT = Path("data/links/setup/git_ssh_protocol_urls.txt")
DEFAULT_RESULTS = Path("data/links/setup/git_ssh_check_results.json")
DEFAULT_ALIVE = Path("data/links/setup/alive_git_ssh_urls.txt")
DEFAULT_DEAD = Path("data/links/setup/dead_git_ssh_urls.txt")


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
    parser = argparse.ArgumentParser(description="Verify git+ssh URLs from a text file.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="File containing git+ssh entries.")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS, help="Path to write JSON results.")
    parser.add_argument("--alive-output", type=Path, default=DEFAULT_ALIVE, help="File to list accessible URLs.")
    parser.add_argument("--dead-output", type=Path, default=DEFAULT_DEAD, help="File to list inaccessible URLs.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Timeout in seconds for each git ls-remote call.")
    parser.add_argument("--keep-revision", action="store_true", help="Include revision when checking via git ls-remote.")
    return parser.parse_args()


def load_links(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if line and not line.startswith("#"):
                yield line


def normalise_git_ssh(raw: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not raw.startswith("git+"):
        return None, None, None

    body = raw[4:]
    main, hash_sep, frag = body.partition("#")

    if "://" not in main:
        return None, None, None
    scheme, rest = main.split("://", 1)

    if rest.startswith("github.com"):
        rest = f"git@{rest}"
    if rest.startswith("git@github.com:"):
        user_host, _, remainder = rest.partition(":")
        rest = f"{user_host}/{remainder}"

    revision = None
    base_rest = rest

    slash_idx = rest.find("/")
    at_idx = rest.rfind("@")
    if slash_idx != -1 and at_idx > slash_idx:
        revision = rest[at_idx + 1 :]
        base_rest = rest[:at_idx]

    remote = f"{scheme}://{base_rest}"
    normalized_main = remote
    if revision:
        normalized_main = f"{normalized_main}@{revision}"

    normalized = f"git+{normalized_main}"
    if hash_sep:
        normalized = f"{normalized}#{frag}"

    return remote, revision, normalized


def run_git_ls_remote(remote: str, revision: Optional[str], timeout: float, include_revision: bool) -> Tuple[bool, Optional[int], Optional[str]]:
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


def check_links(
    links: Iterable[str],
    timeout: float,
    include_revision: bool,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for raw in links:
        remote, revision, normalized = normalise_git_ssh(raw)
        if not remote:
            results.append(CheckResult(raw, normalized, remote, revision, False, None, "unable to parse git+ssh url"))
            continue

        ok, rc, err = run_git_ls_remote(remote, revision, timeout, include_revision)
        results.append(CheckResult(raw, normalized, remote, revision if include_revision else None, ok, rc, err))
    return results


def write_list(path: Path, items: Iterable[str]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(item)
            fh.write("\n")


def main() -> None:
    args = parse_args()
    links = list(load_links(args.input))
    results = check_links(links, args.timeout, args.keep_revision)

    alive = [r.normalized or r.raw for r in results if r.ok]
    dead = [r.normalized or r.raw for r in results if not r.ok]

    args.results.write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")
    write_list(args.alive_output, alive)
    write_list(args.dead_output, dead)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
