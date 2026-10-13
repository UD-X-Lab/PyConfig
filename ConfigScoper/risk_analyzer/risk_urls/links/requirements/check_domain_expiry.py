#!/usr/bin/env python3
"""
Utilities to detect whether domains referenced in `dead_urls.txt` are expired.

The script performs three steps:
1. Extract every URL from the input file (handling lines that contain multiple URLs).
2. Derive the registrable domain for each URL.
3. Query the system `whois` command and DNS to determine whether the domain is still active.

The output is a simple, human-readable report that you can redirect to a file if needed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urlparse

try:
    import dns.resolver as dns_resolver  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    dns_resolver = None

# Matches URL prefixes of the form "<scheme>://", where the scheme may include
# characters such as "+", "." or "-". This allows us to capture entries like
# git+git://, git+ssh://, hg+ssh://, bzr+ssh://, ftp://, s3://, etc.
URL_START_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://")

# Common substrings used in WHOIS responses to denote the expiry date.
WHOIS_EXPIRY_KEYS = (
    "expiry date",
    "expiration date",
    "registry expiry date",
    "renewal date",
    "expire on",
    "expires",
)

# Known date patterns returned by registrars in WHOIS responses.
WHOIS_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%d-%b-%Y",
    "%d-%b-%Y %H:%M:%S",
    "%d-%b-%Y %H:%M:%S%z",
    "%Y.%m.%d %H:%M:%S",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S",
)


@dataclass
class DomainCheckResult:
    domain: str
    urls: List[str]
    status: str
    expires_on: Optional[dt.datetime]
    dns_result: Optional["DNSProbeResult"]
    notes: Optional[str] = None


@dataclass
class DNSProbeResult:
    status: str
    a_records: List[str]
    aaaa_records: List[str]
    ns_records: List[str]
    errors: List[str]


def iter_urls(line: str) -> Iterable[str]:
    """Yield individual URLs on a line, even if they were concatenated."""
    matches = list(URL_START_RE.finditer(line))
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
        raw_url = line[start:end].strip().strip("'\"`")
        # Strip trailing characters that can't belong to a URL.
        raw_url = raw_url.rstrip(",;)")
        if raw_url:
            yield raw_url


def extract_domain(url: str) -> Optional[str]:
    """Return the bare domain portion of a URL (lowercased), or None on failure."""
    candidate = url

    # Many URLs have composite schemes like git+https:// or hg+ssh://.
    # Split on the first "+" and keep the portion after it so that urlparse
    # can understand the actual network protocol segment.
    if "+" in candidate.split("://", 1)[0]:
        candidate = candidate.split("+", 1)[1]

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None

    if not parsed.netloc:
        # Handle scp-style git syntax without an explicit scheme, e.g.
        # git@github.com:org/repo
        if "@" in candidate and ":" in candidate.split("@")[-1]:
            host_part = candidate.split("@", 1)[-1].split(":", 1)[0]
            return host_part.lower()
        return None

    # Remove user info (e.g. git+https://user@domain/repo.git) and ports.
    host = parsed.netloc.split("@")[-1].split(":")[0].lower()
    return host or None


def load_domains(url_file: Path) -> dict[str, List[str]]:
    """Read the file and map domains to the URLs that referenced them."""
    domain_map: dict[str, List[str]] = defaultdict(list)
    with url_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            for url in iter_urls(line):
                domain = extract_domain(url)
                if domain:
                    domain_map[domain].append(url)
    return domain_map


def run_whois(domain: str) -> Optional[str]:
    """Return raw WHOIS text for a domain, or None if the command failed."""
    try:
        completed = subprocess.run(
            ["whois", domain],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError:
        raise RuntimeError("The `whois` command is not installed on this system")
    except subprocess.TimeoutExpired:
        return None

    if completed.returncode != 0:
        return None
    return completed.stdout


def parse_expiry_date(whois_text: str) -> Optional[dt.datetime]:
    """Try to extract an expiration date from WHOIS output."""
    for raw_line in whois_text.splitlines():
        lower = raw_line.lower()
        if not any(key in lower for key in WHOIS_EXPIRY_KEYS):
            continue

        _, _, raw_value = raw_line.partition(":")
        candidate = raw_value.strip()
        if not candidate:
            continue

        # WHOIS often returns multiple space-separated values; the first token is
        # typically the date, so try that first while keeping the original string
        # as a fallback.
        for value in (candidate.split()[0], candidate):
            parsed = try_parse_datetime(value)
            if parsed:
                return parsed
    return None


def try_parse_datetime(value: str) -> Optional[dt.datetime]:
    """Parse a datetime string using known WHOIS formats."""
    for fmt in WHOIS_DATE_FORMATS:
        try:
            parsed = dt.datetime.strptime(value, fmt)
        except ValueError:
            continue

        # Normalize to aware UTC when no timezone information is supplied.
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    return None


def check_dns(domain: str) -> Optional[DNSProbeResult]:
    """Probe DNS using dnspython; return structured results or None if unavailable."""
    if dns_resolver is None:
        return None

    resolver = dns_resolver.Resolver()
    resolver.timeout = 5.0
    resolver.lifetime = 5.0

    a_records: List[str] = []
    aaaa_records: List[str] = []
    errors: List[str] = []

    for record_type, target in (("A", a_records), ("AAAA", aaaa_records)):
        try:
            answers = resolver.resolve(domain, record_type, lifetime=5.0)
        except dns_resolver.NXDOMAIN as exc:
            errors.append(f"{record_type}:{exc.__class__.__name__}")
            return DNSProbeResult(
                status="nxdomain",
                a_records=a_records,
                aaaa_records=aaaa_records,
                ns_records=[],
                errors=errors,
            )
        except dns_resolver.NoAnswer as exc:
            errors.append(f"{record_type}:{exc.__class__.__name__}")
            continue
        except dns_resolver.NoNameservers as exc:
            errors.append(f"{record_type}:{exc.__class__.__name__}")
            continue
        except Exception as exc:  # pragma: no cover - unexpected
            errors.append(f"{record_type}:{exc.__class__.__name__}")
            continue
        else:
            target.extend(str(item).rstrip(".") for item in answers)

    if a_records or aaaa_records:
        return DNSProbeResult(
            status="has-address",
            a_records=a_records,
            aaaa_records=aaaa_records,
            ns_records=[],
            errors=errors,
        )

    ns_records: List[str] = []
    try:
        answers = resolver.resolve(domain, "NS", lifetime=5.0)
    except dns_resolver.NXDOMAIN as exc:
        errors.append(f"NS:{exc.__class__.__name__}")
        return DNSProbeResult(
            status="nxdomain",
            a_records=a_records,
            aaaa_records=aaaa_records,
            ns_records=[],
            errors=errors,
        )
    except dns_resolver.NoAnswer as exc:
        errors.append(f"NS:{exc.__class__.__name__}")
    except dns_resolver.NoNameservers as exc:
        errors.append(f"NS:{exc.__class__.__name__}")
    except Exception as exc:  # pragma: no cover - unexpected
        errors.append(f"NS:{exc.__class__.__name__}")
    else:
        ns_records = [str(item).rstrip(".") for item in answers]

    if ns_records:
        return DNSProbeResult(
            status="delegated",
            a_records=a_records,
            aaaa_records=aaaa_records,
            ns_records=ns_records,
            errors=errors,
        )

    return DNSProbeResult(
        status="no-ns",
        a_records=a_records,
        aaaa_records=aaaa_records,
        ns_records=ns_records,
        errors=errors,
    )


def classify_domain(expiry: Optional[dt.datetime], dns_result: Optional[DNSProbeResult]) -> str:
    """Derive a status string based on WHOIS and DNS data."""
    now = dt.datetime.now(dt.timezone.utc)

    if expiry:
        if expiry < now:
            return "expired"
        if expiry < now + dt.timedelta(days=30):
            return "expiring-soon"
        return "active"

    if dns_result:
        if dns_result.status == "has-address":
            return "active (dns-only)"
        if dns_result.status == "delegated":
            return "active (dns-delegated)"
        if dns_result.status == "nxdomain":
            return "likely-expired"
    return "unknown"


def check_domain(domain: str, urls: List[str]) -> DomainCheckResult:
    """Collect WHOIS + DNS information and classify a domain."""
    whois_text = None
    notes = None
    try:
        whois_text = run_whois(domain)
    except RuntimeError as err:
        notes = str(err)

    expiry = parse_expiry_date(whois_text) if whois_text else None
    dns_result = check_dns(domain)
    status = classify_domain(expiry, dns_result)

    if whois_text is None and not notes:
        notes = "WHOIS lookup unavailable or timed out"
    elif expiry is None and whois_text:
        notes = "WHOIS returned no recognizable expiry date"
    if dns_result is None:
        notes = (
            f"{notes}; DNS lookup skipped (dnspython not installed)"
            if notes
            else "DNS lookup skipped (dnspython not installed)"
        )
    elif dns_result.errors:
        error_note = "DNS errors: " + ", ".join(dns_result.errors)
        notes = f"{notes}; {error_note}" if notes else error_note

    return DomainCheckResult(
        domain=domain,
        urls=urls,
        status=status,
        expires_on=expiry,
        dns_result=dns_result,
        notes=notes,
    )


def format_result(result: DomainCheckResult) -> str:
    """Format a DomainCheckResult for display."""
    expiry = (
        result.expires_on.isoformat()
        if result.expires_on
        else "unknown"
    )
    if result.dns_result:
        dns_state = result.dns_result.status
        detail_parts = [
            f"A:{len(result.dns_result.a_records)}",
            f"AAAA:{len(result.dns_result.aaaa_records)}",
            f"NS:{len(result.dns_result.ns_records)}",
        ]
        if result.dns_result.errors:
            detail_parts.append("errors:" + "|".join(result.dns_result.errors[:3]))
        dns_text = f"{dns_state} ({', '.join(detail_parts)})"
    else:
        dns_text = "unavailable"
    note_text = f"  note: {result.notes}" if result.notes else ""
    return (
        f"{result.domain:40}  status={result.status:16}  "
        f"expiry={expiry:25}  dns={dns_text}{note_text}"
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Determine whether domains in dead_urls.txt are still valid.",
    )
    parser.add_argument(
        "url_file",
        nargs="?",
        type=Path,
        default=Path("data/links/requirements/dead_urls.txt"),
        help="Path to the file that contains candidate URLs.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("data/links/summary/domain_expiry_report.json"),
        help="Where to write the JSON report (default: data/links/summary/domain_expiry_report.json).",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("data/links/summary/domain_expiry_summary.txt"),
        help="Where to write the textual summary (default: data/links/summary/domain_expiry_summary.txt).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if not args.url_file.exists():
        print(f"Input file not found: {args.url_file}", file=sys.stderr)
        return 1

    domain_map = load_domains(args.url_file)
    if not domain_map:
        print("No domains found.", file=sys.stderr)
        return 1

    print(f"Found {len(domain_map)} unique domains. Checking...")
    print("-" * 90)

    results = []
    for domain, urls in sorted(domain_map.items()):
        result = check_domain(domain, urls)
        results.append(result)
        print(format_result(result))

    print("-" * 90)
    active = sum(1 for item in results if item.status.startswith("active"))
    expired = sum(1 for item in results if "expired" in item.status)
    unknown = len(results) - active - expired
    print(
        f"Summary: active={active}, expired={expired}, unknown={unknown}, "
        f"total={len(results)}"
    )

    output_dir = args.json_output.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = [
        {
            "domain": item.domain,
            "status": item.status,
            "expires_on": item.expires_on.isoformat() if item.expires_on else None,
            "dns_status": item.dns_result.status if item.dns_result else None,
            "dns_a_records": item.dns_result.a_records if item.dns_result else [],
            "dns_aaaa_records": item.dns_result.aaaa_records if item.dns_result else [],
            "dns_ns_records": item.dns_result.ns_records if item.dns_result else [],
            "dns_errors": item.dns_result.errors if item.dns_result else [],
            "notes": item.notes,
            "urls": item.urls,
        }
        for item in results
    ]
    args.json_output.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    expired_domains = [
        item.domain
        for item in results
        if "expired" in item.status
    ]

    summary_lines = [
        f"total={len(results)}",
        f"active={active}",
        f"expired={expired}",
        f"unknown={unknown}",
        "",
        "expired_domains:",
        *sorted(expired_domains),
    ]
    args.summary_output.write_text("\n".join(summary_lines), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
