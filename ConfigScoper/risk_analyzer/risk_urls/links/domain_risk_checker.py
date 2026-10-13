#!/usr/bin/env python3
"""
Detect potential domain takeover or expiration issues for VCS/HTTP URLs.

The script extracts domains from an input list of URLs (supporting git/ssh/http/https),
then performs lightweight checks:
  - DNS resolution (socket.getaddrinfo)
  - Optional `dig` lookup to inspect CNAME/A records for takeover-prone hosts
  - Optional `whois` query to determine expiration date

Because these checks rely on DNS/WHOIS, results may be limited in sandboxed
environments without external network access or missing utilities.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

DEFAULT_INPUT = Path("data/links/summary/requirements/dead_git_urls.txt")
DEFAULT_OUTPUT_DIR = Path("data/links/domain_risk")

TAKEOVER_HOST_HINTS = [
    "github.io",
    "githubusercontent.com",
    "herokuapp.com",
    "herokudns.com",
    "amazonaws.com",
    "github.com",
    "azurewebsites.net",
    "cloudfront.net",
    "fastly.net",
    "pantheon.io",
    "readme.io",
    "zendesk.com",
    "unbouncepages.com",
]

WHOIS_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%d-%b-%Y",
    "%d-%b-%Y %H:%M:%S",
]


@dataclass
class DomainRiskResult:
    url: str
    category: str
    domain: Optional[str]
    dns_ok: Optional[bool]
    dns_reason: str
    takeover_risk: Optional[bool]
    takeover_reason: str
    expired: Optional[bool]
    expiry_date: Optional[str]
    expiry_reason: str

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "category": self.category,
            "domain": self.domain,
            "dns_ok": self.dns_ok,
            "dns_reason": self.dns_reason,
            "takeover_risk": self.takeover_risk,
            "takeover_reason": self.takeover_reason,
            "expired": self.expired,
            "expiry_date": self.expiry_date,
            "expiry_reason": self.expiry_reason,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyse domains for takeover/expiration risk.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="File containing URLs.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for reports.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout for network-related calls.")
    parser.add_argument(
        "--include-http",
        action="store_true",
        help="If set, include http/https URLs (default only git/ssh).",
    )
    return parser.parse_args()


def load_urls(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            url = raw.strip()
            if url and not url.startswith("#"):
                yield url


def categorize(url: str, include_http: bool) -> Optional[str]:
    lower = url.lower()
    if lower.startswith(("git+ssh://", "ssh://", "git://", "git+git://")):
        return "git"
    if include_http:
        if lower.startswith("https://"):
            return "https"
        if lower.startswith("http://"):
            return "http"
    return None


def extract_domain(url: str) -> Optional[str]:
    candidate = url
    if candidate.startswith("git+"):
        candidate = candidate[len("git+") :]

    if "://" in candidate:
        parsed = urlparse(candidate)
        host = parsed.netloc
        if not host and parsed.path:
            # handle scp-style after removing scheme
            candidate = parsed.path
        else:
            if "@" in host:
                host = host.split("@", 1)[1]
            if ":" in host:
                host = host.split(":", 1)[0]
            return host or None

    if "@" in candidate and ":" in candidate.split("@")[-1]:
        return candidate.split("@", 1)[-1].split(":", 1)[0]

    return None


def dns_check(domain: Optional[str], timeout: float) -> Tuple[Optional[bool], str]:
    if not domain:
        return None, "unable to parse domain"
    socket.setdefaulttimeout(timeout)
    try:
        socket.getaddrinfo(domain, None)
        return True, "domain resolves"
    except socket.gaierror as exc:
        return False, f"DNS resolution failed: {exc}"
    except socket.timeout:
        return False, "DNS lookup timed out"
    except Exception as exc:  # pragma: no cover - unexpected
        return None, f"unexpected DNS error: {exc}"


def dig_lookup(domain: str, timeout: float) -> Tuple[Optional[bool], str]:
    try:
        completed = subprocess.run(
            ["dig", "+short", domain],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return None, "dig not available"
    except subprocess.TimeoutExpired:
        return None, "dig timed out"

    if completed.returncode != 0:
        return None, completed.stderr.strip() or "dig failed"

    output = completed.stdout.strip().splitlines()
    if not output:
        return True, "no DNS answer (potential risk)"

    for line in output:
        lowered = line.lower()
        for hint in TAKEOVER_HOST_HINTS:
            if hint in lowered:
                return True, f"points to takeover-prone host ({hint})"
    return False, "no obvious takeover indicators"


def parse_expiry_date(text: str) -> Optional[datetime]:
    normalized = text.strip()
    for fmt in WHOIS_DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def whois_check(domain: Optional[str], timeout: float) -> Tuple[Optional[bool], Optional[str], str]:
    if not domain:
        return None, None, "no domain"

    try:
        completed = subprocess.run(
            ["whois", domain],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return None, None, "whois not available"
    except subprocess.TimeoutExpired:
        return None, None, "whois timed out"

    if completed.returncode != 0:
        return None, None, completed.stderr.strip() or "whois query failed"

    expiry_date: Optional[datetime] = None
    for line in completed.stdout.splitlines():
        lowered = line.lower()
        if "expire" in lowered or "expiry" in lowered or "expiration" in lowered or "renewal date" in lowered:
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            parsed = parse_expiry_date(parts[1])
            if parsed:
                expiry_date = parsed
                break

    if not expiry_date:
        return None, None, "expiry date not found"

    expired = expiry_date < datetime.utcnow()
    return expired, expiry_date.isoformat(), "parsed from WHOIS"


def main() -> None:
    args = parse_args()
    results: list[DomainRiskResult] = []

    for url in load_urls(args.input):
        category = categorize(url, include_http=args.include_http)
        if category is None:
            continue

        domain = extract_domain(url)
        dns_ok, dns_reason = dns_check(domain, args.timeout)
        takeover_risk, takeover_reason = (None, "dns check failed")

        if dns_ok is True:
            takeover_risk, takeover_reason = dig_lookup(domain, args.timeout)

        expired, expiry_date, expiry_reason = whois_check(domain, args.timeout * 2)

        results.append(
            DomainRiskResult(
                url=url,
                category=category,
                domain=domain,
                dns_ok=dns_ok,
                dns_reason=dns_reason,
                takeover_risk=takeover_risk,
                takeover_reason=takeover_reason,
                expired=expired,
                expiry_date=expiry_date,
                expiry_reason=expiry_reason,
            )
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "domain_risk_report.json"
    output_path.write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")

    # Write simple text summary
    summary_path = args.output_dir / "domain_risk_summary.txt"
    with summary_path.open("w", encoding="utf-8") as fh:
        for result in results:
            status = []
            if result.dns_ok is False:
                status.append("DNS_FAIL")
            if result.takeover_risk:
                status.append("TAKEOVER?")
            if result.expired is True:
                status.append("EXPIRED")
            fh.write(
                f"[{result.category.upper()}] {result.domain or '<unknown>'} :: "
                f"{', '.join(status) if status else 'OK'} :: {result.url}\n"
            )


if __name__ == "__main__":
    main()
