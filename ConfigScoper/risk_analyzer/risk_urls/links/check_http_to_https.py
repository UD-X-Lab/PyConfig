#!/usr/bin/env python3

import argparse
import sys
import requests
from urllib.parse import urlparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_WORKERS = 10
DEFAULT_TIMEOUT = 8.0

def try_head_then_get(session, url, timeout):

    try:
        # HEAD first
        resp = session.head(url, allow_redirects=True, timeout=timeout)
        # Some servers respond to HEAD with method not allowed -> fallback
        if resp.status_code in (405, 501):
            resp = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
        return True, resp.url, resp.status_code, None
    except requests.exceptions.RequestException as e:
        # fallback try GET once more if HEAD failed in a way that might be transient
        # (but don't loop forever)
        try:
            resp = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
            return True, resp.url, resp.status_code, None
        except requests.exceptions.RequestException as e2:
            return False, None, None, str(e2)

def check_one(url, timeout, include_errors, verbose=False):
    parsed = urlparse(url)
    if parsed.scheme.lower() != "http":
        return {"input": url, "is_http": False, "converted": None, "final": None, "status": None, "error": "not-http-scheme"}

    session = requests.Session()
    # some servers may require a user-agent
    session.headers.update({"User-Agent": "check-http-to-https/1.0"})
    ok, final, status, err = try_head_then_get(session, url, timeout)
    if not ok:
        if verbose:
            print(f"[ERR] {url} -> request failed: {err}", file=sys.stderr)
        # if include_errors True, treat failure as "not converted"
        return {
            "input": url,
            "is_http": True,
            "converted": False if include_errors else None,
            "final": None,
            "status": None,
            "error": err,
        }
    # got final URL
    final_scheme = urlparse(final).scheme.lower()
    converted = (final_scheme == "https")
    if verbose:
        print(f"[OK] {url} -> final={final} (status={status}) converted={converted}", file=sys.stderr)
    return {
        "input": url,
        "is_http": True,
        "converted": converted,
        "final": final,
        "status": status,
        "error": None,
    }

def main():
    p = argparse.ArgumentParser(description="Check whether http:// URLs redirect to https://")
    p.add_argument("--input", "-i", help="input file (one URL per line). If omitted reads stdin.")
    p.add_argument("--out", "-o", help="output file to write URLs that do NOT convert to https (one per line).")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"concurrency workers (default {DEFAULT_WORKERS})")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"request timeout seconds (default {DEFAULT_TIMEOUT})")
    p.add_argument("--include-errors", action="store_true", help="treat request errors/timeouts as 'not converted' and include them in output")
    p.add_argument("--verbose", action="store_true", help="print progress and debug info to stderr")
    args = p.parse_args()

    # read urls
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f]
    else:
        lines = [ln.strip() for ln in sys.stdin]

    # filter and dedupe while preserving order
    seen = OrderedDict()
    for ln in lines:
        if not ln:
            continue
        # only consider lines that start with http:// (case-insensitive)
        if ln.lower().startswith("http://"):
            if ln not in seen:
                seen[ln] = None

    urls = list(seen.keys())
    if not urls:
        print("No http:// URLs found in input.", file=sys.stderr)
        return

    if args.verbose:
        print(f"Checking {len(urls)} http:// URLs with {args.workers} workers, timeout={args.timeout}s", file=sys.stderr)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(check_one, u, args.timeout, args.include_errors, args.verbose): u for u in urls}
        for fut in as_completed(futs):
            try:
                res = fut.result()
            except Exception as exc:
                # unexpected
                url = futs[fut]
                if args.verbose:
                    print(f"[EXC] {url} -> {exc}", file=sys.stderr)
                results.append({"input": url, "is_http": True, "converted": None, "final": None, "status": None, "error": str(exc)})
            else:
                results.append(res)

    # extract those NOT converted to https
    not_converted = []
    for r in results:
        # r["converted"] == False means explicitly ended on http (or treated error as not converted)
        # r["converted"] == None means ignored (error and include_errors==False)
        if r["converted"] is False:
            not_converted.append((r["input"], r["final"], r["status"], r["error"]))
        elif r["converted"] is None:
            # request failed and user didn't opt to include errors -> skip
            pass

    # print summary
    converted_count = sum(1 for r in results if r["converted"] is True)
    failed_count = sum(1 for r in results if r["error"])
    explicit_http = len(not_converted)
    total = len(results)

    print(f"Total checked: {total}")
    print(f"Converted to https: {converted_count}")
    print(f"Explicitly stayed on http or treated as http (included): {explicit_http}")
    print(f"Requests with errors: {failed_count}")

    # print list to stdout
    if explicit_http:
        print("\nURLs that did NOT convert to https (input, final_url, status, error):")
        for u, final, status, err in not_converted:
            print(u, "\t", final or "-", "\t", status or "-", "\t", err or "-")

    # optionally write only the input URLs (one per line) to output file
    if args.out:
        with open(args.out, "w", encoding="utf-8") as outf:
            for u, final, status, err in not_converted:
                outf.write(u + "\n")
        if args.verbose:
            print(f"Wrote {len(not_converted)} non-https URLs to {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
