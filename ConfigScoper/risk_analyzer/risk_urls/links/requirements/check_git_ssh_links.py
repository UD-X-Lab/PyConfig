#!/usr/bin/env python3
"""
Probe git+ssh style VCS links to see if their remotes (and optional revisions) are accessible.

Given a file such as `git_ssh_protocol_urls.txt`, this script will normalise each line,
run `git ls-remote` to check reachability, and report results in a machine-readable summary.

Example:
    python check_git_ssh_links.py --input git_ssh_protocol_urls.txt --output results.json

By default no network operations are performed unless you execute the script; note that
successful checks require network access and appropriate SSH credentials.
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
from urllib.parse import urlparse

DEFAULT_INPUT = Path("data/links/requirements/git_ssh_protocol_urls.txt")
DEFAULT_BZR_INPUT = Path("data/links/requirements/bzr_ssh_protocol_urls.txt")
DEFAULT_ALIVE_OUTPUT = Path("data/links/requirements/alive_urls.txt")
DEFAULT_DNS_ERROR_OUTPUT = Path("data/links/requirements/git_ssh_dns_errors.json")
DEFAULT_OTHER_ERROR_OUTPUT = Path("data/links/requirements/git_ssh_other_errors.json")
DEFAULT_PRIVATE_LINKS_OUTPUT = Path("data/links/requirements/git_ssh_private_links.json")


@dataclass
class CheckResult:
    raw: str
    normalized: Optional[str]
    remote: Optional[str]
    revision: Optional[str]
    ok: bool
    returncode: Optional[int]
    error: Optional[str]
    vcs: str

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "remote": self.remote,
            "revision": self.revision,
            "ok": self.ok,
            "returncode": self.returncode,
            "error": self.error,
            "vcs": self.vcs,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test git+ssh VCS links using git ls-remote.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="File containing git+ssh entries (one per line).",
    )
    parser.add_argument(
        "--bzr-input",
        type=Path,
        default=DEFAULT_BZR_INPUT,
        help="File containing bzr+ssh entries (one per line). Use '-' to skip.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON results to this path (defaults to stdout).",
    )
    parser.add_argument(
        "--alive-output",
        type=Path,
        default=DEFAULT_ALIVE_OUTPUT,
        help="Append successfully validated (modified) links to this file.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Per-command timeout in seconds.",
    )
    parser.add_argument(
        "--keep-revision",
        action="store_true",
        help="Include revision (if provided) when checking remote (default trims revision).",
    )
    parser.add_argument(
        "--dns-error-json",
        type=Path,
        default=DEFAULT_DNS_ERROR_OUTPUT,
        help="Write Name-or-service-not-known errors to this JSON file.",
    )
    parser.add_argument(
        "--other-error-json",
        type=Path,
        default=DEFAULT_OTHER_ERROR_OUTPUT,
        help="Write all other errors (link, domain, message) to this JSON file.",
    )
    parser.add_argument(
        "--private-links-json",
        type=Path,
        default=DEFAULT_PRIVATE_LINKS_OUTPUT,
        help="Write potential private/access-controlled links (host key or timeout) to this JSON file.",
    )
    return parser.parse_args()


def load_links(path: Path) -> Iterable[str]:
    if path == Path("-"):
        return []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            yield line


def normalise_git_ssh(raw: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not raw.startswith("git+"):
        return None, None, None

    no_scheme = raw[4:]
    main, hash_sep, frag = no_scheme.partition("#")

    scheme_split = main.split("://", 1)
    if len(scheme_split) != 2:
        return None, None, None

    scheme, rest = scheme_split
    if rest.startswith("github.com"):
        rest = f"git@{rest}"
    if rest.startswith("git@github.com:"):
        # Convert SCP-style host:path into ssh://host/path form
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


def run_git_ls_remote(
    remote: str,
    revision: Optional[str],
    timeout: float,
    keep_revision: bool,
) -> Tuple[bool, Optional[int], Optional[str]]:
    args = ["git", "ls-remote", "--exit-code", remote]
    if keep_revision and revision:
        args.append(revision)

    env = os.environ.copy()
    existing = env.get("GIT_SSH_COMMAND")
    ssh_cmd = existing or "ssh"
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

    error_message = (completed.stderr or completed.stdout or "").strip()
    return False, completed.returncode, error_message or "unknown git error"


def check_links(
    links: Iterable[str],
    timeout: float,
    keep_revision: bool,
) -> Iterable[CheckResult]:
    for raw in links:
        remote, revision, normalized = normalise_git_ssh(raw)
        if not remote:
            yield CheckResult(raw, normalized, remote, revision, False, None, "unable to parse git+ssh url", "git")
            continue

        ok, returncode, error = run_git_ls_remote(remote, revision, timeout, keep_revision)
        yield CheckResult(raw, normalized, remote, revision, ok, returncode, error, "git")


def append_alive_links(path: Path, links: Iterable[str]) -> None:
    to_add = [link for link in links if link]
    if not to_add:
        return

    existing: set[str] = set()
    if path.exists():
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            existing = {line.rstrip("\n") for line in fh}

    new_entries = [link for link in to_add if link not in existing]
    if not new_entries:
        return

    with path.open("a", encoding="utf-8") as fh:
        for entry in new_entries:
            fh.write(entry)
            fh.write("\n")


def extract_domain(remote: Optional[str]) -> Optional[str]:
    if not remote:
        return None
    parsed = urlparse(remote)
    netloc = parsed.netloc
    if not netloc:
        return None
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]
    if ":" in netloc:
        netloc = netloc.split(":", 1)[0]
    return netloc or None


def normalise_bzr_ssh(raw: str) -> Tuple[Optional[str], Optional[str]]:
    if not raw.startswith("bzr+ssh://"):
        return None, None
    remote, hash_sep, frag = raw.partition("#")
    normalized = remote if not hash_sep else f"{remote}#{frag}"
    return remote, normalized


def run_bzr_info(remote: str, timeout: float) -> Tuple[bool, Optional[int], Optional[str]]:
    args = ["bzr", "info", remote]
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
        return False, None, "bzr executable not found"

    if completed.returncode == 0:
        return True, 0, None

    error_message = (completed.stderr or completed.stdout or "").strip()
    return False, completed.returncode, error_message or "unknown bzr error"


def check_bzr_links(
    links: Iterable[str],
    timeout: float,
) -> Iterable[CheckResult]:
    for raw in links:
        remote, normalized = normalise_bzr_ssh(raw)
        if not remote:
            yield CheckResult(raw, normalized, remote, None, False, None, "unable to parse bzr+ssh url", "bzr")
            continue

        ok, returncode, error = run_bzr_info(remote, timeout)
        yield CheckResult(raw, normalized, remote, None, ok, returncode, error, "bzr")


def main() -> None:
    args = parse_args()
    results: list[CheckResult] = []

    git_links = list(load_links(args.input)) if args.input and args.input != Path("-") else []
    results.extend(check_links(git_links, args.timeout, args.keep_revision))

    if args.bzr_input and args.bzr_input != Path("-") and args.bzr_input.exists():
        bzr_links = list(load_links(args.bzr_input))
        results.extend(check_bzr_links(bzr_links, args.timeout))
    elif args.bzr_input and args.bzr_input != Path("-") and not args.bzr_input.exists():
        print(f"Warning: bzr input file {args.bzr_input} not found", file=sys.stderr)

    success_links = [r.normalized for r in results if r.ok and r.normalized]
    append_alive_links(args.alive_output, success_links)

    dns_errors = []
    other_errors = []
    private_errors = []
    for r in results:
        if r.ok or not r.error:
            continue
        domain = extract_domain(r.remote)
        entry_link = r.normalized or r.raw
        if "name or service not known" in r.error.lower():
            dns_errors.append(
                {
                    "link": entry_link,
                    "domain": domain,
                }
            )
        else:
            lowered_error = r.error.lower()
            if "host key verification failed" in lowered_error or "timeout after 5.0s" in lowered_error:
                private_errors.append(
                    {
                        "link": entry_link,
                        "domain": domain,
                        "error": r.error,
                    }
                )
            other_errors.append(
                {
                    "link": entry_link,
                    "domain": domain,
                    "error": r.error,
                }
            )

    if args.dns_error_json:
        args.dns_error_json.write_text(json.dumps(dns_errors, indent=2), encoding="utf-8")
    if args.other_error_json:
        args.other_error_json.write_text(json.dumps(other_errors, indent=2), encoding="utf-8")
    if args.private_links_json:
        args.private_links_json.write_text(json.dumps(private_errors, indent=2), encoding="utf-8")

    output_payload = {
        "total": len(results),
        "ok": sum(1 for r in results if r.ok),
        "failed": sum(1 for r in results if not r.ok),
        "results": [r.to_dict() for r in results],
    }

    if args.output:
        args.output.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
    else:
        json.dump(output_payload, sys.stdout, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
