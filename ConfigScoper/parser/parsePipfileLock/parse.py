from pathlib import Path
import json
from typing import Any, List, Dict, Tuple, Optional
from collections import defaultdict, Counter
import re

# toml parsing: tomllib for py3.11+, tomli fallback
try:
    import tomllib  # type: ignore
    toml_loads = lambda s: tomllib.loads(s)
    TOML_BACKEND = "tomllib"
except Exception:
    try:
        import tomli  # type: ignore
        toml_loads = lambda s: tomli.loads(s)
        TOML_BACKEND = "tomli"
    except Exception:
        toml_loads = None
        TOML_BACKEND = None

# URL regex (tolerant)
URL_RE = re.compile(r"[A-Za-z0-9+\-_.]+://[^\s'\"),\]]+")

def extract_urls_from_value(value: Any) -> List[str]:
    """Recursively extract URL-like strings from Python objects (str/list/dict)."""
    urls: List[str] = []
    if isinstance(value, str):
        urls.extend(URL_RE.findall(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            urls.extend(extract_urls_from_value(k))
            urls.extend(extract_urls_from_value(v))
    elif isinstance(value, (list, tuple, set)):
        for elt in value:
            urls.extend(extract_urls_from_value(elt))
    # dedupe preserving order
    return list(dict.fromkeys(urls))

def process_pipfile_lock(path: Path) -> Tuple[Dict[str, Any], str]:
    """
    Robust parser for Pipfile.lock files.
    Returns (fields, status). On parse failure returns empty dict and status describing why.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {}, f"read_error:{e}"

    if not raw.strip():
        return {}, "empty"

    # Try normal parse
    try:
        data = json.loads(raw)
        status = "json_parsed"
    except Exception:
        # Try to sanitize (drop leading comment lines, extract {..} substring, etc.)
        sanitized = sanitize_json_text(raw)
        if sanitized is None:
            # give some diagnostic info in status - include small prefix for debugging
            preview = raw.strip()[:200].replace("\n", "\\n")
            return {}, f"json_parse_error:unparseable (preview={preview})"
        try:
            data = json.loads(sanitized)
            status = "json_sanitized_parsed"
        except Exception as e:
            preview = sanitized.strip()[:200].replace("\n", "\\n")
            return {}, f"json_parse_error_after_sanitize:{e} (preview={preview})"

    # At this point `data` is a parsed JSON object
    fields: Dict[str, Any] = {}

    # _meta.sources.url  -> data["_meta"]["sources"] -> list of dicts with "url"
    meta = data.get("_meta") or {}
    if isinstance(meta, dict):
        sources = meta.get("sources") or []
        if isinstance(sources, list):
            urls = []
            for s in sources:
                if isinstance(s, dict) and "url" in s:
                    urls.append(s["url"])
            if urls:
                fields["lock._meta.sources.url"] = {
                    "value_repr": json.dumps(urls, ensure_ascii=False),
                    "resolved": True,
                    "resolved_value": urls,
                    "urls": list(dict.fromkeys(urls)),
                }

    # nested "default" -> "charset-normalizer" -> "package" -> "git"
    def safe_nested_get(d: Dict[str, Any], path_list):
        cur = d
        for p in path_list:
            if not isinstance(cur, dict) or p not in cur:
                return None
            cur = cur[p]
        return cur

    val = safe_nested_get(data, ["default", "charset-normalizer", "package", "git"])
    if val is not None:
        fields["lock.default.charset-normalizer.package.git"] = {
            "value_repr": json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val,
            "resolved": True,
            "resolved_value": val,
            "urls": extract_urls_from_value(val) if 'extract_urls_from_value' in globals() else [],
        }

    # convenience: scan default/develop for any URL appearing in package entries
    for topk in ("default", "develop"):
        section = data.get(topk)
        if isinstance(section, dict):
            for pkg_name, pkg_info in section.items():
                urls = []
                # reuse your extract_urls_from_value if present; otherwise a small fallback
                if 'extract_urls_from_value' in globals():
                    urls = extract_urls_from_value(pkg_info)
                else:
                    if isinstance(pkg_info, str):
                        urls = URL_RE.findall(pkg_info)
                    elif isinstance(pkg_info, dict):
                        for v in pkg_info.values():
                            if isinstance(v, str):
                                urls.extend(URL_RE.findall(v))
                if urls:
                    fk = f"lock.{topk}.{pkg_name}"
                    fields.setdefault(fk, {
                        "value_repr": json.dumps(pkg_info, ensure_ascii=False) if not isinstance(pkg_info, str) else pkg_info,
                        "resolved": True,
                        "resolved_value": pkg_info,
                        "urls": []
                    })
                    for u in urls:
                        if u not in fields[fk]["urls"]:
                            fields[fk]["urls"].append(u)

    return fields, status

def sanitize_json_text(raw: str) -> Optional[str]:
    """
    Try to produce a sane JSON substring from raw text.
    - strip BOM
    - drop leading comment lines that start with '#'
    - strip leading/trailing whitespace
    - if direct json.loads succeeds, return text
    - otherwise try to find first '{' and last '}' and return the substring if it parses
    - return None if nothing parseable found
    """
    if not raw:
        return None

    # strip BOM
    txt = raw.lstrip("\ufeff")

    # drop leading comment lines that begin with '#'
    lines = txt.splitlines()
    i = 0
    while i < len(lines) and lines[i].lstrip().startswith("#"):
        i += 1
    txt = "\n".join(lines[i:]).strip()

    if not txt:
        return None

    # try direct parse first
    try:
        json.loads(txt)
        return txt
    except Exception:
        pass

    # If the file contains HTML (e.g. 404 page), quick detect and bail
    if txt.lstrip().startswith("<"):
        # Definitely not JSON (HTML page); no point trying substring
        return None

    # Try to find the largest balanced JSON object candidate using first '{' and last '}'
    first = txt.find("{")
    last = txt.rfind("}")
    if 0 <= first < last:
        candidate = txt[first:last+1]
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            # try a slightly smaller window: find the first '{' and the first '}' after it, iterate
            # (this is best-effort only)
            # attempt to find any substring that parses as JSON
            for start_idx in range(0, first+1):
                if txt.find("{", start_idx) == -1:
                    break
                s = txt.find("{", start_idx)
                for end_idx in range(len(txt)-1, s, -1):
                    if txt[end_idx] != "}":
                        continue
                    cand = txt[s:end_idx+1]
                    try:
                        json.loads(cand)
                        return cand
                    except Exception:
                        continue
    return None

def aggregate(root: Path) -> Dict[str, Any]:
    """
    Walk root for Pipfile and Pipfile.lock, aggregate stats and file-level details.
    Returns a serializable dict.
    """
    root = Path(root).resolve()
    # find files
    pipfileLock_paths = list(root.rglob("*"))
    total_files = len(pipfileLock_paths)
    print(f"Found {len(pipfileLock_paths)} Pipfile.lock under {root} (total {total_files})")

    # Aggregates
    field_counts: Counter = Counter()
    field_files: Dict[str, List[str]] = defaultdict(list)
    url_sources_by_field: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    files_detail: Dict[str, Dict[str, Any]] = {}

    processed = 0
    for p in pipfileLock_paths:
        processed += 1
        print(f"[{processed}/{total_files}] Processing {p} ...", end=" ")
        try:
            # if "pipfile" in p.name:
            # fields, status = process_pipfile(p)
            # else:
            fields, status = process_pipfile_lock(p)
        except Exception as e:
            print(f"error:{e}")
            continue

        print(status)
        if not fields:
            continue

        file_key = str(p)
        files_detail[file_key] = {"fields": {}}

        # per-file dedupe: ensure each field counts once per file
        for fk, info in fields.items():
            # increment count once per file
            field_counts[fk] += 1
            field_files[fk].append(file_key)

            urls: List[str] = info.get("urls", []) or []
            # dedupe urls in this file+field
            unique_urls = list(dict.fromkeys(urls))
            files_detail[file_key]["fields"][fk] = {
                "value_repr": info.get("value_repr"),
                "resolved": bool(info.get("resolved", False)),
                "resolved_value": info.get("resolved_value", None),
                "urls": unique_urls,
            }
            for u in unique_urls:
                url_sources_by_field[fk][u].add(file_key)

    # build url_counter_by_field
    url_counter_by_field: Dict[str, Dict[str, int]] = {}
    url_sources_serial: Dict[str, Dict[str, List[str]]] = {}
    for fk, urlmap in url_sources_by_field.items():
        url_counter_by_field[fk] = {u: len(srcs) for u, srcs in urlmap.items()}
        url_sources_serial[fk] = {u: sorted(list(srcs)) for u, srcs in urlmap.items()}

    result = {
        "scan_root": str(root),
        "summary": {
            "total_lockfiles": len(pipfileLock_paths),
            "total_files_processed": processed,
        },
        "field_counts": dict(field_counts),
        "field_files": dict(field_files),
        "files": files_detail,
        "url_counter_by_field": url_counter_by_field,
        "url_sources_by_field": url_sources_serial,
        "parser_backend": TOML_BACKEND,
    }
    return result

def main():   
    root = Path("/home/hello/finder/ConfigScoper/BigQueryData/configFiles/Pipfile.lock")
    result = aggregate(root)

    outp = Path("/home/hello/finder/ConfigScoper/parser/parsePipfileLock/output/pipfileLock_statistic.json")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote JSON result to", outp.resolve())

if __name__ == "__main__":
    main()