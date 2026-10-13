#!/usr/bin/env python3
"""
Split `invalid_urls.txt` entries into protocol-specific buckets.

Usage examples:
    python extract_git_protocol_links.py
    python extract_git_protocol_links.py --input custom.txt --git-git-output git_git.txt \
        --git-ssh-output git_ssh.txt --hg-ssh-output hg_ssh.txt --bzr-ssh-output bzr_ssh.txt
"""

from __future__ import annotations

import argparse
from pathlib import Path

GIT_GIT_PREFIX = "git+git://"
GIT_SSH_PREFIX = "git+ssh://"
HG_SSH_PREFIX = "hg+ssh://"
BZR_SSH_PREFIX = "bzr+ssh://"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract git-protocol VCS URLs into a separate file.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/links/requirements/invalid_urls.txt"),
        help="Path to the source text file.",
    )
    parser.add_argument(
        "--git-git-output",
        type=Path,
        default=Path("data/links/requirements/git_git_protocol_urls.txt"),
        help="Destination file for git+git:// URLs.",
    )
    parser.add_argument(
        "--git-ssh-output",
        type=Path,
        default=Path("data/links/requirements/git_ssh_protocol_urls.txt"),
        help="Destination file for git+ssh:// URLs.",
    )
    parser.add_argument(
        "--hg-ssh-output",
        type=Path,
        default=Path("data/links/requirements/hg_ssh_protocol_urls.txt"),
        help="Destination file for hg+ssh:// URLs.",
    )
    parser.add_argument(
        "--bzr-ssh-output",
        type=Path,
        default=Path("data/links/requirements/bzr_ssh_protocol_urls.txt"),
        help="Destination file for bzr+ssh:// URLs.",
    )
    parser.add_argument(
        "--rest-output",
        type=Path,
        default=Path("data/links/requirements/non_git_protocol_urls.txt"),
        help="Destination file for all other entries.",
    )
    return parser.parse_args()


def split_urls(
    input_path: Path,
    git_git_output_path: Path,
    git_ssh_output_path: Path,
    hg_ssh_output_path: Path,
    bzr_ssh_output_path: Path,
    rest_output_path: Path,
) -> None:
    git_git_lines: list[str] = []
    git_ssh_lines: list[str] = []
    hg_ssh_lines: list[str] = []
    bzr_ssh_lines: list[str] = []
    rest_lines: list[str] = []

    with input_path.open("r", encoding="utf-8", errors="replace") as src:
        for raw_line in src:
            line = raw_line.rstrip("\n")
            if line.startswith(GIT_GIT_PREFIX):
                git_git_lines.append(line)
            elif line.startswith(GIT_SSH_PREFIX):
                git_ssh_lines.append(line)
            elif line.startswith(HG_SSH_PREFIX):
                hg_ssh_lines.append(line)
            elif line.startswith(BZR_SSH_PREFIX):
                bzr_ssh_lines.append(line)
            else:
                rest_lines.append(line)

    git_git_output_path.write_text("\n".join(git_git_lines) + ("\n" if git_git_lines else ""), encoding="utf-8")
    git_ssh_output_path.write_text("\n".join(git_ssh_lines) + ("\n" if git_ssh_lines else ""), encoding="utf-8")
    hg_ssh_output_path.write_text("\n".join(hg_ssh_lines) + ("\n" if hg_ssh_lines else ""), encoding="utf-8")
    bzr_ssh_output_path.write_text("\n".join(bzr_ssh_lines) + ("\n" if bzr_ssh_lines else ""), encoding="utf-8")
    rest_output_path.write_text("\n".join(rest_lines) + ("\n" if rest_lines else ""), encoding="utf-8")


def main() -> None:
    args = parse_args()
    split_urls(
        args.input,
        args.git_git_output,
        args.git_ssh_output,
        args.hg_ssh_output,
        args.bzr_ssh_output,
        args.rest_output,
    )


if __name__ == "__main__":
    main()
