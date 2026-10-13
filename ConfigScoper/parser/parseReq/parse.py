from __future__ import annotations
from collections import Counter, defaultdict
import json
from tqdm import tqdm
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Iterable
import re
from dataclasses import dataclass, asdict

VCS_URL_RE = re.compile(
    r"""
    (?P<full>
        (?P<vcs>git|hg|svn|bzr)\+
        (?P<scheme>https?|ssh|git|file)://
        (?P<rest>[^\s]+)
    )
    """, re.IGNORECASE | re.VERBOSE,
)
EGG_RE = re.compile(r"(?:^|[#&])egg=(?P<egg>[^&/#]+)", re.IGNORECASE)
REF_RE  = re.compile(r"@(?P<ref>[^#]+)")

@dataclass
class VCSLink:
    vcs: str
    url: str
    ref: Optional[str]
    egg: Optional[str]
    raw: str

@dataclass
class DirectFileLink:
    url: str
    ext: str

DIRECT_FILE_EXTS = (
    "tar.gz", "tar.bz2", "tar.xz", "tgz", "tbz2",
    "zip", "whl", "tar", "gz", "xz", "bz2"
)
_direct_ext_group = "|".join(re.escape(ext) for ext in DIRECT_FILE_EXTS)
DIRECT_FILE_URL_RE = re.compile(
    rf"""
    (?P<url>
        (?P<scheme>https?|ftp)://
        [^\s'\"]+?\.(?P<ext>{_direct_ext_group})
        (?:[?#][^\s'\"]*)?
    )
    """, re.IGNORECASE | re.VERBOSE,
)

def _read_text_safely(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"Failed to read {p}: {e}")
        return ""

def _join_line_continuations(lines: List[str]) -> List[str]:
    """
    Merge lines ending with backslash '\' into a single logical line.
    """
    merged = []
    buf = ""
    for ln in lines:
        s = ln.rstrip("\n")
        if not buf:
            buf = s
        else:
            buf += s
        if buf.endswith("\\"):
            buf = buf[:-1]  # drop the backslash, continue with next physical line
        else:
            merged.append(buf)
            buf = ""
    if buf:
        merged.append(buf)
    return merged

def _strip_inline_comment(raw: str) -> str:
    """
    Remove pip-style inline comments that start with a '#' preceded by whitespace,
    while leaving URL fragments (e.g., '#egg=...') intact.
    """
    for m in re.finditer(r"#", raw):
        i = m.start()
        if i == 0 or raw[i - 1].isspace():
            return raw[:i].rstrip()
    return raw.rstrip()

def _has_vcs_commit(s: str) -> Tuple[bool, str]:
    """
    Returns (bool, reason). bool indicates if the line looks like a VCS req pinned with @<rev>.
    The reason explains what was detected.
    """
    t = s.strip()
    # Only consider VCS schemes; editable (-e) allowed
    m = re.search(r"(?i)(?:^|\s)(?:-e\s+)?((?:git|hg|svn|bzr)\+([^ \t#]+))", t)
    if not m:
        return (False, "not a VCS requirement")
    url = m.group(1)  # e.g., git+ssh://git@github.com/user/repo.git@abc123
    # Optional: if it looks like a hex-ish commit, great; but accept any non-empty ref/branch/tag
    return (True, f"{url} detected")

def _extract_require_files(line: str) -> List[str]:
    """
    Extract files from -r/--requirement occurrences. Accept any non-space token as path/URL.
    e.g., '-r base.txt', '--requirement=requirements/prod.txt'
    """
    files = []
    # --requirement=FILE or --requirement FILE
    for m in re.finditer(r"(?<!\S)--requirement(?:=(\S+)|\s+(\S+))", line):
        files.append(m.group(1) or m.group(2))
    # -r FILE (short form does NOT allow '='); allow multiple occurrences
    for m in re.finditer(r"(?<!\S)-r\s+(\S+)", line):
        files.append(m.group(1))
    return files

def _extract_constraint_files(line: str) -> List[str]:
    """
    Extract files from -c/--constraint occurrences. Accept any non-space token as path/URL.
    """
    files = []
    for m in re.finditer(r"(?<!\S)--constraint(?:=(\S+)|\s+(\S+))", line):
        files.append(m.group(1) or m.group(2))
    for m in re.finditer(r"(?<!\S)-c\s+(\S+)", line):
        files.append(m.group(1))
    return files

def _extract_find_links(line: str) -> List[str]:
    vals: List[str] = []
    for m in re.finditer(r"(?<!\S)--find-links(?:=(\S+)|\s+(\S+))", line):
        vals.append(m.group(1) or m.group(2))
    # -f URL
    for m in re.finditer(r"(?<!\S)-f\s+(\S+)", line):
        vals.append(m.group(1))
    return vals

def _extract_global_option(line: str) -> List[str]:
    vals: List[str] = []
    pattern = re.compile(
        r'''(?<!\S)--global-option(?:=
                (?:"([^"]+)"|'([^']+)'|(\S+))      
            |\s+
                (?:"([^"]+)"|'([^']+)'|(\S+))      
            )''',
        re.VERBOSE
    )
    for m in pattern.finditer(line):
        for g in (1, 2, 3, 4, 5, 6):
            v = m.group(g)
            if v is not None:
                vals.append(v)
                break
    return vals

def _extract_index_url(line: str) -> List[str]:
    vals: List[str] = []
    pat = re.compile(
        r'''(?:
                (?<!\S)--index-url(?:=(?:"([^"]+)"|'([^']+)'|(\S+))|\s+(?:"([^"]+)"|'([^']+)'|(\S+)))
            |
                (?<!\S)-i\s+(?:"([^"]+)"|'([^']+)'|(\S+))
            )''',
        re.VERBOSE | re.IGNORECASE
    )
    for m in pat.finditer(line):
        for g in range(1, 10):
            v = m.group(g)
            if v is not None:
                vals.append(v)
                break
    return vals

def _extract_extra_index_url(line: str) -> List[str]:
    vals: List[str] = []
    pat = re.compile(
        r'''(?<!\S)--extra-index-url(?:=
                (?:"([^"]+)"|'([^']+)'|(\S+))
            |\s+
                (?:"([^"]+)"|'([^']+)'|(\S+))
            )''',
        re.VERBOSE | re.IGNORECASE
    )
    for m in pat.finditer(line):
        for g in range(1, 7):
            v = m.group(g)
            if v is not None:
                vals.append(v)
                break
    return vals

def _extract_trusted_host(line: str) -> List[str]:
    vals: List[str] = []
    pat = re.compile(
        r'''(?<!\S)--trusted-host(?:=
                (?:"([^"]+)"|'([^']+)'|(\S+))
            |\s+
                (?:"([^"]+)"|'([^']+)'|(\S+))
            )''',
        re.VERBOSE | re.IGNORECASE
    )
    for m in pat.finditer(line):
        for g in range(1, 6+1):
            v = m.group(g)
            if v is not None:
                vals.append(v)
                break
    return vals

def extract_vcs_links(text: str) -> List[VCSLink]:
    out: List[VCSLink] = []
    for m in VCS_URL_RE.finditer(text):
        vcs = m.group("vcs").lower()
        scheme = m.group("scheme")
        rest = m.group("rest")
        raw = m.group("full")
        url_full = f"{scheme}://{rest}"
        egg = (EGG_RE.search(url_full).group("egg")
               if EGG_RE.search(url_full) else None)
        ref = (REF_RE.search(url_full).group("ref")
               if REF_RE.search(url_full) else None)
        out.append(VCSLink(vcs=vcs, url=url_full, ref=ref, egg=egg, raw=raw))
    return out

def extract_direct_file_links(text: str) -> List[DirectFileLink]:
    return [DirectFileLink(url=m.group("url"), ext=m.group("ext"))
            for m in DIRECT_FILE_URL_RE.finditer(text)]

def _has_option(line: str, opt: str) -> bool:
    # Match the exact long option token. Allow '=', or whitespace argument, or end-of-line.
    # Examples: "--find-links=https://...", "--find-links https://...", "--no-index"
    return re.search(rf"(?<!\S){re.escape(opt)}(?:\s|=|$)", line) is not None

def analyze_requirements(text: str, source_file: str) -> List[dict]:
    physical = text.splitlines()
    logical = _join_line_continuations(physical)
    results = []
    for idx, raw in enumerate(logical, start=1):
        stripped_comment = _strip_inline_comment(raw)
        normalized = stripped_comment.strip()
        if not normalized:
            continue

        vcs, reason = _has_vcs_commit(normalized)
        req_files = _extract_require_files(normalized)
        con_files = _extract_constraint_files(normalized)
        find_links_vals = _extract_find_links(normalized)
        global_option_vals = _extract_global_option(normalized) 
        index_url_vals = _extract_index_url(normalized)
        extra_index_vals = _extract_extra_index_url(normalized)
        trusted_host_vals = _extract_trusted_host(normalized)

        vcs_links = [asdict(v) for v in extract_vcs_links(normalized)]
        direct_links = [asdict(d) for d in extract_direct_file_links(normalized)]

        res = {
            "line_no": idx,
            "source_file": source_file,
            "raw": raw,
            "normalized": normalized,
            "has_vcs_commit": vcs,
            "vcs_links": vcs_links,
            "direct_file_links": direct_links,
            "vcs_reason": reason,

            "has_no_index": _has_option(normalized, "--no-index"),
            "has_find_links": _has_option(normalized, "--find-links") or bool(find_links_vals),
            "find_links_values": find_links_vals,

            "has_global_option": _has_option(normalized, "--global-option") or bool(global_option_vals),
            "global_option_values": global_option_vals,  

            "has_index_url": _has_option(normalized, "--index-url") or _has_option(normalized, "-i") or bool(index_url_vals),
            "index_url_values": index_url_vals,

            "has_extra_index_url": _has_option(normalized, "--extra-index-url") or bool(extra_index_vals),
            "extra_index_url_values": extra_index_vals,

            "has_trusted_host": _has_option(normalized, "--trusted-host") or bool(trusted_host_vals),
            "trusted_host_values": trusted_host_vals,

            "has_require_file": len(req_files) > 0,
            "require_files": req_files,
            "has_constraint_file": len(con_files) > 0,
            "constraint_files": con_files,
        }
        results.append(res)
    return results

def analyze_directory(require_dir: Path) -> List[dict]:
    files = list(require_dir.glob("*.txt"))

    all_results: List[dict] = []
    for fp in tqdm(files, desc=f"scan {require_dir}"):
        text = _read_text_safely(fp)
        if not text.strip():
            continue

        per_file_results = analyze_requirements(text, str(fp))
        for r in per_file_results:
            r["__file__"] = str(fp)
        all_results.extend(per_file_results)
    return all_results

def collect_statistics(results: Iterable[dict]) -> dict:
    stats = {
        "total_lines": 0,

        "vcs_links": {
            "count": 0,
            "by_vcs": Counter(),
            "by_vcs_sources": defaultdict(set),
            "by_url": Counter(),
            "by_url_sources": defaultdict(set),
            "raw_examples": Counter(),
            "raw_sources": defaultdict(set),
        },

        "direct_file_links": {
            "count": 0,
            "by_ext": Counter(),
            "by_ext_sources": defaultdict(set),
            "by_url": Counter(),
            "by_url_sources": defaultdict(set),
        },

        "options": {
            "--no-index": {"count": 0, "sources": set()},
            "--find-links": {"count": 0, "sources": set()},
            "--global-option": {"count": 0, "sources": set()},
            "--index-url": {"count": 0, "sources": set()},
            "--extra-index-url": {"count": 0, "sources": set()},
            "--trusted-host": {"count": 0, "sources": set()},
        },

        "options_detail": {
            "find_links_count": 0,
            "find_links_values": Counter(),
            "find_links_sources": defaultdict(set),

            "global_option_count": 0,
            "global_option_values": Counter(),
            "global_option_sources": defaultdict(set),

            "index_url_count": 0,
            "index_url_values": Counter(),
            "index_url_sources": defaultdict(set),

            "extra_index_url_count": 0,
            "extra_index_url_values": Counter(),
            "extra_index_url_sources": defaultdict(set),

            "trusted_host_count": 0,
            "trusted_host_values": Counter(),
            "trusted_host_sources": defaultdict(set),
        },

        "require_files": Counter(),
        "require_files_sources": defaultdict(set),
        "constraint_files": Counter(),
        "constraint_files_sources": defaultdict(set),
    }

    for r in results:
        stats["total_lines"] += 1
        source_file = r.get("source_file") or ""

        # ---- VCS links ----
        for v in r.get("vcs_links", []):
            stats["vcs_links"]["count"] += 1
            vcs = v.get("vcs")
            url = v.get("url")
            raw = v.get("raw")

            if vcs:
                stats["vcs_links"]["by_vcs"][vcs] += 1
                stats["vcs_links"]["by_vcs_sources"][vcs].add(source_file)

            if url:
                stats["vcs_links"]["by_url"][url] += 1
                stats["vcs_links"]["by_url_sources"][url].add(source_file)

            if raw:
                stats["vcs_links"]["raw_examples"][raw] += 1
                stats["vcs_links"]["raw_sources"][raw].add(source_file)

        # ---- Direct file links ----
        for d in r.get("direct_file_links", []):
            stats["direct_file_links"]["count"] += 1
            ext = d.get("ext")
            url = d.get("url")

            if ext:
                stats["direct_file_links"]["by_ext"][ext] += 1
                stats["direct_file_links"]["by_ext_sources"][ext].add(source_file)

            if url:
                stats["direct_file_links"]["by_url"][url] += 1
                stats["direct_file_links"]["by_url_sources"][url].add(source_file)

        # ---- Options presence (per line) + sources ----
        if r.get("has_no_index"):
            stats["options"]["--no-index"]["count"] += 1
            stats["options"]["--no-index"]["sources"].add(source_file)
        if r.get("has_find_links"):
            stats["options"]["--find-links"]["count"] += 1
            stats["options"]["--find-links"]["sources"].add(source_file)
        if r.get("has_global_option"):
            stats["options"]["--global-option"]["count"] += 1
            stats["options"]["--global-option"]["sources"].add(source_file)
        if r.get("has_index_url"):
            stats["options"]["--index-url"]["count"] += 1
            stats["options"]["--index-url"]["sources"].add(source_file)
        if r.get("has_extra_index_url"):
            stats["options"]["--extra-index-url"]["count"] += 1
            stats["options"]["--extra-index-url"]["sources"].add(source_file)
        if r.get("has_trusted_host"):
            stats["options"]["--trusted-host"]["count"] += 1
            stats["options"]["--trusted-host"]["sources"].add(source_file)

        # ---- Option values + sources ----
        for val in r.get("find_links_values", []) or []:
            stats["options_detail"]["find_links_count"] += 1
            stats["options_detail"]["find_links_values"][val] += 1
            stats["options_detail"]["find_links_sources"][val].add(source_file)

        for val in r.get("global_option_values", []) or []:
            stats["options_detail"]["global_option_count"] += 1
            stats["options_detail"]["global_option_values"][val] += 1
            stats["options_detail"]["global_option_sources"][val].add(source_file)

        for val in r.get("index_url_values", []) or []:
            stats["options_detail"]["index_url_count"] += 1
            stats["options_detail"]["index_url_values"][val] += 1
            stats["options_detail"]["index_url_sources"][val].add(source_file)

        for val in r.get("extra_index_url_values", []) or []:
            stats["options_detail"]["extra_index_url_count"] += 1
            stats["options_detail"]["extra_index_url_values"][val] += 1
            stats["options_detail"]["extra_index_url_sources"][val].add(source_file)

        for val in r.get("trusted_host_values", []) or []:
            stats["options_detail"]["trusted_host_count"] += 1
            stats["options_detail"]["trusted_host_values"][val] += 1
            stats["options_detail"]["trusted_host_sources"][val].add(source_file)

        # ---- -r / -c targets + sources ----
        for f in r.get("require_files", []):
            stats["require_files"][f] += 1
            stats["require_files_sources"][f].add(source_file)

        for f in r.get("constraint_files", []):
            stats["constraint_files"][f] += 1
            stats["constraint_files_sources"][f].add(source_file)

    def _clean_counter(c: Counter):
        return {str(k): v for k, v in c.items() if k is not None}

    def _clean_sources(d: Dict[str, set]):
        return {str(k): sorted(v) for k, v in d.items() if k is not None}

    out = {
        "total_lines": stats["total_lines"],

        "vcs_links": {
            "count": stats["vcs_links"]["count"],
            "by_vcs": _clean_counter(stats["vcs_links"]["by_vcs"]),
            "by_vcs_sources": _clean_sources(stats["vcs_links"]["by_vcs_sources"]),
            "by_url_top": stats["vcs_links"]["by_url"],
            "by_url_sources": _clean_sources(stats["vcs_links"]["by_url_sources"]),
            "raw_examples_top": stats["vcs_links"]["raw_examples"],
            "raw_sources": _clean_sources(stats["vcs_links"]["raw_sources"]),
        },

        "direct_file_links": {
            "count": stats["direct_file_links"]["count"],
            "by_ext": _clean_counter(stats["direct_file_links"]["by_ext"]),
            "by_ext_sources": _clean_sources(stats["direct_file_links"]["by_ext_sources"]),
            "by_url_top": stats["direct_file_links"]["by_url"],
            "by_url_sources": _clean_sources(stats["direct_file_links"]["by_url_sources"]),
        },

        "options": {
            k: {
                "count": v["count"],
                "sources": sorted(v["sources"])
            }
            for k, v in stats["options"].items()
        },

        "options_detail": {
            "find_links_count": stats["options_detail"]["find_links_count"],
            "find_links_values_top": stats["options_detail"]["find_links_values"],
            "find_links_sources": _clean_sources(stats["options_detail"]["find_links_sources"]),

            "global_option_count": stats["options_detail"]["global_option_count"],
            "global_option_values_top": stats["options_detail"]["global_option_values"],
            "global_option_sources": _clean_sources(stats["options_detail"]["global_option_sources"]),

            "index_url_count": stats["options_detail"]["index_url_count"],
            "index_url_values_top": stats["options_detail"]["index_url_values"],
            "index_url_sources": _clean_sources(stats["options_detail"]["index_url_sources"]),

            "extra_index_url_count": stats["options_detail"]["extra_index_url_count"],
            "extra_index_url_values_top": stats["options_detail"]["extra_index_url_values"],
            "extra_index_url_sources": _clean_sources(stats["options_detail"]["extra_index_url_sources"]),

            "trusted_host_count": stats["options_detail"]["trusted_host_count"],
            "trusted_host_values_top": stats["options_detail"]["trusted_host_values"],
            "trusted_host_sources": _clean_sources(stats["options_detail"]["trusted_host_sources"]),
        },

        "require_files_top": stats["require_files"],
        "require_files_sources": _clean_sources(stats["require_files_sources"]),
        "constraint_files_top": stats["constraint_files"],
        "constraint_files_sources": _clean_sources(stats["constraint_files_sources"]),
    }
    return out


def statistic_fields_in_directory(require_dir: Path, out_path) -> dict:
    results = analyze_directory(require_dir)
    stats = collect_statistics(results)
    with open(out_path, "w", encoding="utf-8") as outf:
        json.dump(stats, outf, indent=2, ensure_ascii=False)
    print(f"[OK] Statistics written to {out_path}")
    print(f"Total logical lines analyzed: {stats['total_lines']}")
    print(f"Total VCS links found: {stats['vcs_links']['count']}")
    print(f"Total direct file links found: {stats['direct_file_links']['count']}")
    print(f"Total lines with --no-index: {stats['options']['--no-index']}")
    print(f"Total lines with --find-links: {stats['options']['--find-links']}")
    print(f"Total find-links targets counted: {stats['options_detail']['find_links_count']}")
    return stats

if __name__ == "__main__":
    root = Path("/home/hello/finder/ConfigScoper/BigQueryData/configFiles/requirements")

    outp = Path("/home/hello/finder/ConfigScoper/parser/parseReq/output/req_statistic.json")
    statistic_fields_in_directory(root, outp)
    