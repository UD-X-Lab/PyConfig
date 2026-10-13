#!/usr/bin/env python3
"""
Validate pipfile invalid URLs such as git://, git+ssh://, ssh://, and s3://.

For git/ssh remotes we use `git ls-remote`. For S3 URIs we rely on the AWS CLI
(`aws s3 ls ...`). Results are written to JSON plus companion alive/dead lists.
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

DEFAULT_INPUT = Path("data/links/pipfile/invalid_urls.txt")
DEFAULT_RESULTS = Path("data/links/pipfile/check_results.json")
DEFAULT_ALIVE = Path("data/links/pipfile/alive_urls.txt")
DEFAULT_DEAD = Path("data/links/pipfile/dead_urls.txt")

GIT_PREFIXES = ("git://", "git+ssh://", "ssh://")
S3_PREFIX = "s3://"


@dataclass
class CheckResult:
    url: str
    kind: str
    normalized: Optional[str]
    ok: bool
    returncode: Optional[int]
    error: Optional[str]

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "kind": self.kind,
            "normalized": self.normalized,
            "ok": self.ok,
            "returncode": self.returncode,
            "error": self.error,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check accessibility of pipfile invalid URLs.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Source list of URLs.")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS, help="JSON report path.")
    parser.add_argument("--alive-output", type=Path, default=DEFAULT_ALIVE, help="File for alive URLs.")
    parser.add_argument("--dead-output", type=Path, default=DEFAULT_DEAD, help="File for dead URLs.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Command timeout in seconds.")
    parser.add_argument("--keep-revision", action="store_true", help="Use revision when probing git remotes.")
    return parser.parse_args()


def load_urls(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            url = raw.strip()
            if url and not url.startswith("#"):
                yield url


def classify_url(url: str) -> str:
    if url.startswith(S3_PREFIX):
        return "s3"
    if url.startswith(GIT_PREFIXES):
        return "git"
    return "other"


def normalise_git_url(url: str) -> Tuple[str, Optional[str], str]:
    normalized = url
    revision = None

    if url.startswith("git+"):
        body = url[len("git+") :]
    else:
        body = url

    main, hash_sep, frag = body.partition("#")

    if "@" in main.rsplit("/", 1)[-1]:
        # Git form like ...repo.git@sha -> treat as revision
        repo_part, _, rev = main.rpartition("@")
        if "/" in repo_part:
            main = repo_part
            revision = rev

    remote = main
    if not url.startswith("git+"):
        normalized = f"git+{main}"
    else:
        normalized = url if not hash_sep else f"git+{main}#{frag}"

    return remote, revision, normalized


def run_git_check(remote: str, revision: Optional[str], timeout: float, include_revision: bool) -> Tuple[bool, Optional[int], Optional[str]]:
    args = ["git", "ls-remote", "--exit-code", remote]
    if include_revision and revision:
        args.append(revision)

    env = os.environ.copy()
    ssh_cmd = env.get("GIT_SSH_COMMAND", "ssh")
    if "-o BatchMode" not in ssh_cmd:
        ssh_cmd = f"{ssh_cmd} -o BatchMode=yes"
    env["GIT_SSH_COMMAND"] = ssh_cmd

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

    message = (completed.stderr or completed.stdout or "").strip()
    return False, completed.returncode, message or "unknown git error"


def run_s3_check(url: str, timeout: float) -> Tuple[bool, Optional[int], Optional[str]]:
    args = ["aws", "s3", "ls", url]
    try:
        completed = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return False, None, f"timeout after {timeout:.1f}s"
    except FileNotFoundError:
        return False, None, "aws cli not found"

    if completed.returncode == 0:
        return True, 0, None

    message = (completed.stderr or completed.stdout or "").strip()
    return False, completed.returncode, message or "unknown aws error"


def write_list(path: Path, urls: Iterable[str]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for url in urls:
            fh.write(url)
            fh.write("\n")


def main() -> None:
    args = parse_args()
    results: list[CheckResult] = []

    for url in load_urls(args.input):
        kind = classify_url(url)

        if kind == "git":
            remote, revision, normalized = normalise_git_url(url)
            ok, rc, err = run_git_check(remote, revision, args.timeout, args.keep_revision)
            results.append(CheckResult(url, kind, normalized, ok, rc, err))
        elif kind == "s3":
            ok, rc, err = run_s3_check(url, args.timeout)
            results.append(CheckResult(url, kind, url, ok, rc, err))
        else:
            results.append(CheckResult(url, kind, url, False, None, "unsupported URL type"))

    args.results.write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")

    alive = [r.normalized or r.url for r in results if r.ok]
    dead = [r.normalized or r.url for r in results if not r.ok]
    write_list(args.alive_output, alive)
    write_list(args.dead_output, dead)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
