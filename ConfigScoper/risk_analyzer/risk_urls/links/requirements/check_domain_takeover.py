#!/usr/bin/env python3
"""
Detect domains that might be vulnerable to takeover.

The script performs four key tasks:
1. Read a requirements-style file (default: dead_urls.txt) and extract every URL.
2. Derive the unique domains referenced by those URLs.
3. Probe DNS (CNAME/A/AAAA/NS) and, optionally, HTTP responses for each domain.
4. Classify every domain into risk buckets such as `likely-takeover`, `misconfigured`,
   or `available-for-registration`.

Every probe is best-effort: if optional dependencies are missing or network access fails,
the script degrades gracefully and records the reason in the output notes.
"""
from __future__ import annotations

import argparse
import dataclasses
import http.client
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

try:  # Optional dependency for richer DNS probing
    import dns.resolver as dns_resolver  # type: ignore
except ImportError:  # pragma: no cover - optional
    dns_resolver = None

try:  # Optional dependency for simpler HTTP probing
    import requests  # type: ignore
except ImportError:  # pragma: no cover - optional
    requests = None


# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

DEFAULT_INPUT_PATH = Path("data/links/requirements/dead_urls.txt")
DNS_TIMEOUT_SECONDS = 5.0
HTTP_TIMEOUT_SECONDS = 6.0
HTTP_READ_LIMIT = 4096  # bytes


@dataclasses.dataclass(frozen=True)
class TakeoverPattern:
    """Lookup entry that links a provider to the strings we expect in error pages."""

    needle: str
    provider: str
    signatures: Tuple[str, ...]


KNOWN_TAKEOVER_PATTERNS: Tuple[TakeoverPattern, ...] = (
    TakeoverPattern("github.io", "GitHub Pages", ("There isn't a GitHub Pages site here.", "Repository not found")),
    TakeoverPattern("githubusercontent.com", "GitHub", ("Not Found", "404")),
    TakeoverPattern("amazonaws.com", "AWS S3 Bucket", ("NoSuchBucket", "The specified bucket does not exist")),
    TakeoverPattern("cloudfront.net", "AWS CloudFront", ("The request could not be satisfied", "Bad request")),
    TakeoverPattern("herokudns.com", "Heroku", ("no such app", "there is no such app")),
    TakeoverPattern(".azurewebsites.net", "Azure Web App", ("This web app is stopped", "Resource not found")),
    TakeoverPattern(".azureedge.net", "Azure CDN", ("Error 404", "Resource Not Found")),
    TakeoverPattern("fastly.net", "Fastly", ("Fastly error", "unknown domain")),
    TakeoverPattern("wordpress.com", "WordPress", ("Domain has been deleted", "do you want to register")),
)

# ------------------------------------------------------------------------------
# Data containers
# ------------------------------------------------------------------------------


@dataclasses.dataclass
class DNSProbe:
    status: str
    a_records: List[str]
    aaaa_records: List[str]
    cname_chain: List[str]
    ns_records: List[str]
    errors: List[str]


@dataclasses.dataclass
class HTTPProbe:
    status: str
    code: Optional[int]
    reason: Optional[str]
    signature_match: Optional[str]
    errors: List[str]


@dataclasses.dataclass
class TakeoverFinding:
    domain: str
    urls: List[str]
    risk: str
    provider: Optional[str]
    dns: Optional[DNSProbe]
    http: Optional[HTTPProbe]
    notes: Optional[str]


# ------------------------------------------------------------------------------
# URL and domain extraction helpers
# ------------------------------------------------------------------------------

URL_FINDER = re.compile(r"(?:git\+|hg\+)?https?://", re.IGNORECASE)


def extract_urls(line: str) -> Iterable[str]:
    """
    Yield every URL embedded in a raw requirements line.

    Some datasets concatenate multiple URLs on the same line without separators;
    scanning for protocol prefixes avoids mis-parsing those cases.
    """
    matches = list(URL_FINDER.finditer(line))
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
        candidate = line[start:end].strip().strip("'\"`").rstrip(",;)")
        if candidate:
            yield candidate


def extract_domain(url: str) -> Optional[str]:
    """Return the bare hostname for a URL (lowercase, without credentials or ports)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if not parsed.netloc:
        return None
    host = parsed.netloc.split("@")[-1].split(":")[0].lower()
    return host or None


def collect_domains(url_file: Path) -> Dict[str, List[str]]:
    """Read the input file and build a mapping {domain -> [original URLs]}."""
    domain_map: Dict[str, List[str]] = defaultdict(list)
    with url_file.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            for url in extract_urls(raw_line):
                domain = extract_domain(url)
                if domain:
                    domain_map[domain].append(url)
    return domain_map


# ------------------------------------------------------------------------------
# DNS probing
# ------------------------------------------------------------------------------

def probe_dns(domain: str) -> Optional[DNSProbe]:
    """Query DNS records for a domain and summarize the results."""
    if dns_resolver is None:
        return None

    resolver = dns_resolver.Resolver()
    resolver.timeout = DNS_TIMEOUT_SECONDS
    resolver.lifetime = DNS_TIMEOUT_SECONDS

    a_records: List[str] = []
    aaaa_records: List[str] = []
    cname_chain: List[str] = []
    ns_records: List[str] = []
    errors: List[str] = []
    saw_nxdomain = False

    for record_type, bucket in (
        ("CNAME", cname_chain),
        ("A", a_records),
        ("AAAA", aaaa_records),
        ("NS", ns_records),
    ):
        try:
            answers = resolver.resolve(domain, record_type, lifetime=DNS_TIMEOUT_SECONDS)
        except dns_resolver.NXDOMAIN as exc:
            errors.append(f"{record_type}:{exc.__class__.__name__}")
            saw_nxdomain = True
            continue
        except dns_resolver.NoAnswer as exc:
            # No CNAME is a normal situation; record others for context.
            if record_type != "CNAME":
                errors.append(f"{record_type}:{exc.__class__.__name__}")
            continue
        except dns_resolver.NoNameservers as exc:
            errors.append(f"{record_type}:{exc.__class__.__name__}")
            continue
        except Exception as exc:  # pragma: no cover - unexpected resolver behaviour
            errors.append(f"{record_type}:{exc.__class__.__name__}")
            continue
        else:
            bucket.extend(str(item).rstrip(".") for item in answers)

    if saw_nxdomain and not (a_records or aaaa_records or cname_chain or ns_records):
        return DNSProbe(
            status="nxdomain",
            a_records=[],
            aaaa_records=[],
            cname_chain=[],
            ns_records=[],
            errors=errors,
        )

    status = "ok"
    if not (a_records or aaaa_records) and cname_chain:
        status = "cname-only"
    elif not (a_records or aaaa_records or cname_chain):
        status = "no-address"

    return DNSProbe(
        status=status,
        a_records=a_records,
        aaaa_records=aaaa_records,
        cname_chain=cname_chain,
        ns_records=ns_records,
        errors=errors,
    )


# ------------------------------------------------------------------------------
# HTTP probing
# ------------------------------------------------------------------------------

def detect_signature(body: str) -> Optional[str]:
    """Return the provider whose signature appears in the response body, if any."""
    lowered = body.lower()
    for pattern in KNOWN_TAKEOVER_PATTERNS:
        if any(snippet.lower() in lowered for snippet in pattern.signatures):
            return pattern.provider
    return None


def probe_http(domain: str) -> HTTPProbe:
    """Fetch the root URL of a domain and check for takeover fingerprints."""
    errors: List[str] = []
    code: Optional[int] = None
    reason: Optional[str] = None
    signature: Optional[str] = None

    for scheme in ("https://", "http://"):
        url = f"{scheme}{domain}"

        if requests is not None:
            try:
                response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)  # type: ignore[call-arg]
                body = response.text
                code = response.status_code
                reason = response.reason
            except requests.exceptions.RequestException as exc:  # type: ignore[attr-defined]
                errors.append(exc.__class__.__name__)
                continue
        else:
            try:
                with urllib.request.urlopen(  # type: ignore[arg-type]
                    url,
                    timeout=HTTP_TIMEOUT_SECONDS,
                    context=ssl.create_default_context(),
                ) as resp:
                    code = resp.getcode()
                    reason = resp.reason
                    body = resp.read(HTTP_READ_LIMIT).decode("utf-8", "ignore")
            except (urllib.error.URLError, http.client.HTTPException, socket.error) as exc:
                errors.append(exc.__class__.__name__)
                continue

        signature = detect_signature(body)
        status = "signature-match" if signature else "reachable"
        return HTTPProbe(
            status=status,
            code=code,
            reason=reason,
            signature_match=signature,
            errors=errors,
        )

    # All attempts failed
    return HTTPProbe(
        status="unreachable",
        code=None,
        reason=None,
        signature_match=None,
        errors=errors,
    )


# ------------------------------------------------------------------------------
# Risk assessment
# ------------------------------------------------------------------------------

def lookup_provider(cname_chain: Sequence[str]) -> Optional[Tuple[str, str]]:
    """Return (full_cname, provider) if any CNAME matches known takeover patterns."""
    for cname in cname_chain:
        lowered = cname.lower()
        for pattern in KNOWN_TAKEOVER_PATTERNS:
            if pattern.needle in lowered:
                return cname, pattern.provider
    return None


def assess_takeover_risk(
    dns_result: Optional[DNSProbe],
    http_result: Optional[HTTPProbe],
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Combine DNS and HTTP signals into a risk label.

    Returns (risk, provider, note).
    """
    if dns_result is None:
        return "unknown", None, "DNS lookup skipped (dnspython not installed)"

    provider_match = lookup_provider(dns_result.cname_chain)
    provider = provider_match[1] if provider_match else None

    if dns_result.status == "nxdomain":
        return "available-for-registration", provider, None

    if provider_match:
        cname_target = provider_match[0]
        if http_result and http_result.signature_match:
            return "likely-takeover", provider, f"HTTP signature matched {http_result.signature_match}"
        if not dns_result.a_records and not dns_result.aaaa_records:
            return "possible-takeover", provider, f"CNAME {cname_target} without address records"
        if http_result and http_result.status == "unreachable":
            return "possible-takeover", provider, "HTTP unreachable despite delegation to known provider"

    if not dns_result.a_records and not dns_result.aaaa_records and dns_result.ns_records:
        return "misconfigured", provider, "Domain delegated but returns no address records"

    return "unlikely", provider, None


# ------------------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------------------

def format_finding(finding: TakeoverFinding) -> str:
    """Render a one-line summary describing the takeover risk for a domain."""
    provider_text = finding.provider or "unknown"
    dns_status = finding.dns.status if finding.dns else "dns-skipped"
    dns_details = (
        f"A:{len(finding.dns.a_records)} "
        f"AAAA:{len(finding.dns.aaaa_records)} "
        f"CNAME:{len(finding.dns.cname_chain)} "
        f"NS:{len(finding.dns.ns_records)}"
        if finding.dns
        else ""
    )
    if finding.http:
        http_state = finding.http.status
        if finding.http.code is not None:
            http_state = f"{http_state} ({finding.http.code})"
    else:
        http_state = "http-skipped"

    note_text = f" note: {finding.notes}" if finding.notes else ""
    return (
        f"{finding.domain:40} risk={finding.risk:18} provider={provider_text:18} "
        f"dns={dns_status:13} {dns_details:33} http={http_state}{note_text}"
    )


# ------------------------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------------------------

def check_domain(domain: str, urls: List[str], skip_http: bool) -> TakeoverFinding:
    """Run DNS/HTTP probes for a single domain and package the result."""
    dns_info = probe_dns(domain)
    http_info = None
    http_error_note = None

    if not skip_http:
        try:
            http_info = probe_http(domain)
        except Exception as exc:  # pragma: no cover - defensive guard
            http_error_note = f"HTTP probing failed: {exc.__class__.__name__}"

    risk, provider, risk_note = assess_takeover_risk(dns_info, http_info)

    notes: List[str] = []
    if risk_note:
        notes.append(risk_note)
    if http_error_note:
        notes.append(http_error_note)
    if dns_info and dns_info.errors:
        notes.append("DNS errors: " + ", ".join(dns_info.errors))
    if http_info and http_info.errors:
        notes.append("HTTP errors: " + ", ".join(http_info.errors))
    if dns_info is None:
        notes.append("DNS results unavailable")

    return TakeoverFinding(
        domain=domain,
        urls=urls,
        risk=risk,
        provider=provider,
        dns=dns_info,
        http=http_info,
        notes="; ".join(notes) if notes else None,
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect potential domain takeover risks in a list of URLs.",
    )
    parser.add_argument(
        "url_file",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Path to the file that contains candidate URLs.",
    )
    parser.add_argument(
        "--no-http",
        action="store_true",
        help="Skip HTTP probing (useful when outbound networking is not permitted).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if not args.url_file.exists():
        print(f"Input file not found: {args.url_file}", file=sys.stderr)
        return 1

    domain_map = collect_domains(args.url_file)
    if not domain_map:
        print("No domains found in input.", file=sys.stderr)
        return 1

    if dns_resolver is None:
        print("Warning: dnspython not installed. DNS probing will be skipped.", file=sys.stderr)
    if args.no_http:
        print("Skipping HTTP probing (--no-http).")

    print(f"Found {len(domain_map)} unique domains. Checking...")
    print("-" * 120)

    findings: List[TakeoverFinding] = []
    for domain, urls in sorted(domain_map.items()):
        finding = check_domain(domain, urls, skip_http=args.no_http)
        findings.append(finding)
        print(format_finding(finding))

    print("-" * 120)
    summary: Dict[str, int] = defaultdict(int)
    for item in findings:
        summary[item.risk] += 1
    summary_text = ", ".join(f"{risk}={count}" for risk, count in sorted(summary.items()))
    print(f"Summary: {summary_text} (total={len(findings)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
