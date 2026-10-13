from pathlib import Path
import json
from typing import Any, List, Dict, Tuple, Optional
from collections import defaultdict, Counter
import re

# URL regex (tolerant)
URL_RE = re.compile(r"[A-Za-z0-9+\-_.]+://[^\s'\"),\]]+")

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

def repr_value(value: Any) -> str:
    """Produce JSON-friendly string for value; fallback to repr when needed."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return repr(value)
    
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

def strip_toml_comments(text: str) -> str:
    """
    Remove TOML comments (# to EOL) while attempting to preserve strings.
    Conservative approach that should be fine for typical Pipfile content.
    """
    out_chars: List[str] = []
    i = 0
    n = len(text)
    in_single = in_double = False
    in_triple_single = in_triple_double = False

    while i < n:
        ch = text[i]

        # triple quote handling
        if not (in_single or in_double or in_triple_single or in_triple_double):
            if text.startswith("'''", i):
                in_triple_single = True
                out_chars.append("'''"); i += 3; continue
            if text.startswith('"""', i):
                in_triple_double = True
                out_chars.append('"""'); i += 3; continue
        elif in_triple_single:
            if text.startswith("'''", i):
                in_triple_single = False
                out_chars.append("'''"); i += 3; continue
            out_chars.append(ch); i += 1; continue
        elif in_triple_double:
            if text.startswith('"""', i):
                in_triple_double = False
                out_chars.append('"""'); i += 3; continue
            out_chars.append(ch); i += 1; continue

        # single/double quote
        if not (in_single or in_double):
            if ch == "'":
                in_single = True; out_chars.append(ch); i += 1; continue
            if ch == '"':
                in_double = True; out_chars.append(ch); i += 1; continue
        else:
            if in_single:
                if ch == "'" and not text.startswith("''", i):
                    in_single = False
                out_chars.append(ch); i += 1; continue
            if in_double:
                if ch == '"' and not text.startswith('""', i):
                    in_double = False
                if ch == "\\" and i + 1 < n:
                    out_chars.append(ch); out_chars.append(text[i+1]); i += 2; continue
                out_chars.append(ch); i += 1; continue

        # if not in string
        if ch == "#":
            # drop until newline, but keep newline
            while i < n and text[i] != "\n":
                i += 1
            if i < n and text[i] == "\n":
                out_chars.append("\n"); i += 1
            continue

        out_chars.append(ch); i += 1

    return "".join(out_chars)


def process_pipfile(path: Path) -> Tuple[Dict[str, Any], str]:
    """
    Parse a Pipfile (TOML). Return (per_file_result, status_message).
    per_file_result: { field_key: {value_repr, resolved True/False, resolved_value(if simple), urls:[] } }
    status: 'parsed:backend' or 'parse_error_fallback'
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        return {}, f"read_error: {e}"

    # Try parsing with toml backend if available
    if toml_loads is not None:
        try:
            parsed = toml_loads(raw)
            # extracted fields dict
            fields: Dict[str, Any] = {}

            # [[source]] -> parsed.get("source") (could be list of tables named 'source')
            srcs = parsed.get("source") or parsed.get("sources") or parsed.get("[[source]]")
            if isinstance(srcs, list):
                urls = []
                for s in srcs:
                    if isinstance(s, dict) and "url" in s:
                        urls.append(s["url"])
                if urls:
                    fields["pipfile.source.url"] = {
                        "value_repr": repr_value(urls),
                        "resolved": True,
                        "resolved_value": urls,
                        "urls": extract_urls_from_value(urls),
                    }
            
            # [packages], [dev-packages], [scripts]
            for k, outkey in (("packages", "pipfile.packages"), ("dev-packages", "pipfile.dev-packages"), ("scripts", "pipfile.scripts")):
                v = parsed.get(k)
                if v is None:
                    # sometimes in Pipfile top-level there may be a "packages" under "tool" or other - we stick to top-level
                    pass
                else:
                    fields[outkey] = {
                        "value_repr": repr_value(v),
                        "resolved": True,
                        "resolved_value": v,
                        "urls": extract_urls_from_value(v),
                    }

            return fields, f"parsed:{TOML_BACKEND}"
        except Exception as e:
            # fall through to text-based fallback
            # we'll try to strip comments and perform conservative extraction
            pass

    # fallback: conservative text-based extraction if parsing not available or failed
    stripped = strip_toml_comments(raw)

    fields = {}
    # find [[source]] blocks: search for lines like [[source]] and subsequent url = "..."
    src_blocks = []
    # simple parser: find occurrences of [[source]] and snippet after it
    for m in re.finditer(r'^\s*\[\[source\]\]\s*$', stripped, re.M):
        start = m.end()
        snippet = stripped[start:start+400]  # limited window
        # find url = "..."
        for um in re.finditer(r'url\s*=\s*(.+)$', snippet, re.M):
            rawval = um.group(1).strip().rstrip(',')
            # strip quotes
            rawval = rawval.strip()
            # remove surrounding quotes if present
            if (rawval.startswith('"') and rawval.endswith('"')) or (rawval.startswith("'") and rawval.endswith("'")):
                rawval = rawval[1:-1]
            src_blocks.append(rawval)
    if src_blocks:
        fields["pipfile.source.url"] = {
            "value_repr": repr_value(src_blocks),
            "resolved": False,
            "resolved_value": None,
            "urls": list(dict.fromkeys([u for v in src_blocks for u in URL_RE.findall(v)])),
        }

    # find tables: [packages], [dev-packages], [scripts]
    def find_table_values(name: str) -> Optional[str]:
        # naive: find line "name = ..." or table [name] then collect next lines
        # try key = { ... } or key = "..." patterns
        m = re.search(r'^\s*\[' + re.escape(name) + r'\]\s*$', stripped, re.M)
        if m:
            # capture next chunk of lines until next table
            start = m.end()
            block = stripped[start:start+2000]
            return block.strip()
        # also support inline key assignments (unlikely for Pipfile packages)
        m2 = re.search(r'^\s*' + re.escape(name) + r'\s*=\s*(.+)$', stripped, re.M)
        if m2:
            return m2.group(1).strip()
        return None

    for name, outkey in (("packages", "pipfile.packages"), ("dev-packages", "pipfile.dev-packages"), ("scripts", "pipfile.scripts")):
        val = find_table_values(name)
        if val:
            fields[outkey] = {
                "value_repr": val[:1000],
                "resolved": False,
                "resolved_value": None,
                "urls": list(dict.fromkeys(URL_RE.findall(val))),
            }

    return fields, "fallback_text"



def aggregate(root: Path) -> Dict[str, Any]:
    """
    Walk root for Pipfile and Pipfile.lock, aggregate stats and file-level details.
    Returns a serializable dict.
    """
    root = Path(root).resolve()
    # find files
    pipfile_paths = list(root.rglob("*"))
    # lock_paths = list(root.rglob("*.lock"))
    # total_files = len(pipfile_paths) + len(lock_paths)
    total_files = len(pipfile_paths)
    # print(f"Found {len(pipfile_paths)} Pipfile and {len(lock_paths)} Pipfile.lock under {root} (total {total_files})")
    print(f"Found {len(pipfile_paths)} Pipfile under {root} (total {total_files})")

    # Aggregates
    field_counts: Counter = Counter()
    field_files: Dict[str, List[str]] = defaultdict(list)
    url_sources_by_field: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    files_detail: Dict[str, Dict[str, Any]] = {}

    processed = 0
    # for p in pipfile_paths + lock_paths:
    for p in pipfile_paths:
        processed += 1
        print(f"[{processed}/{total_files}] Processing {p} ...", end=" ")
        try:
            # if "pipfile" in p.name:
            fields, status = process_pipfile(p)
            # else:
            #     fields, status = process_pipfile_lock(p)
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
            "total_pipfiles": len(pipfile_paths),
            # "total_lockfiles": len(lock_paths),
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
    root = Path("/home/hello/finder/ConfigScoper/BigQueryData/configFiles/Pipfile")
    result = aggregate(root)

    outp = Path("/home/hello/finder/ConfigScoper/parser/parsePipfile/output/pipfile_statistic.json")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote JSON result to", outp.resolve())

if __name__ == "__main__":
    main()

