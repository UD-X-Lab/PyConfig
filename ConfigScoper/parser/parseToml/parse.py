import json
import re
import tomli
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set, Optional, Iterable
from collections import defaultdict, Counter

critical_pyproject_fields = {
    "build-system.requires",
    "dependency-groups",
    "project.dependencies",
    "project.optional-dependencies",
    "tool.poetry.dependencies",
    
    "tool.poetry.source.url",
    
    
    "build-system.build-backend",
    "build-system.backend-path",
    
    "project.scripts",
    "project.entry-points",
    "tool.setuptools.script-files",

    "tool.poetry.scripts",
    "tool.poetry.plugins",
}

# URL regex (tolerant)
URL_RE = re.compile(r"[A-Za-z0-9+\-_.]+://[^\s'\"),\]]+")

# Try to import TOML parser (tomllib for py3.11+, tomli fallback)
try:
    import tomllib  # type: ignore
    toml_loads = lambda s: tomllib.loads(s)
    parse_backend = "tomllib"
except Exception:
    try:
        import tomli  # type: ignore
        toml_loads = lambda s: tomli.loads(s)
        parse_backend = "tomli"
    except Exception:
        toml_loads = None
        parse_backend = None

def repr_value(value: Any) -> str:
    """Return JSON-friendly representation string for a value."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return repr(value)


def safe_parse_toml(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Try to parse TOML text using tomllib/tomli if available.
    Returns (parsed_dict or None, backend_name or None)
    """
    if toml_loads is None:
        return None, None
    try:
        data = toml_loads(text)
        return data, parse_backend
    except Exception:
        return None, parse_backend

def extract_urls_from_value(value: Any) -> List[str]:
    """Recursively extract URL-like strings from a parsed TOML value (list/dict/str)."""
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
    # dedupe preserve order
    return list(dict.fromkeys(urls))

def strip_toml_comments(text: str) -> str:
    """
    Remove TOML comments (# to end-of-line) but preserve content inside strings.
    This is a conservative scanner that tracks single/double/triple-quoted strings.
    """
    out_chars = []
    i = 0
    n = len(text)
    in_single = in_double = False
    in_triple_single = in_triple_double = False

    while i < n:
        ch = text[i]

        # handle triple quotes first
        if not (in_single or in_double or in_triple_single or in_triple_double):
            # possible triple-quote start
            if text.startswith("'''", i):
                in_triple_single = True
                out_chars.append("'''")
                i += 3
                continue
            if text.startswith('"""', i):
                in_triple_double = True
                out_chars.append('"""')
                i += 3
                continue
        elif in_triple_single:
            if text.startswith("'''", i):
                in_triple_single = False
                out_chars.append("'''")
                i += 3
                continue
            else:
                out_chars.append(ch)
                i += 1
                continue
        elif in_triple_double:
            if text.startswith('"""', i):
                in_triple_double = False
                out_chars.append('"""')
                i += 3
                continue
            else:
                out_chars.append(ch)
                i += 1
                continue

        # handle single/double quoted strings
        if not (in_single or in_double):
            if ch == "'":
                in_single = True
                out_chars.append(ch)
                i += 1
                continue
            if ch == '"':
                in_double = True
                out_chars.append(ch)
                i += 1
                continue
        else:
            # inside single-quoted string
            if in_single:
                if ch == "'" and not text.startswith("''", i):  # naive end-of-single
                    in_single = False
                out_chars.append(ch)
                i += 1
                continue
            # inside double-quoted string
            if in_double:
                if ch == '"' and not text.startswith('""', i):
                    in_double = False
                # handle escapes in double strings: skip the escape char and include next char
                if ch == "\\" and i + 1 < n:
                    out_chars.append(ch)
                    out_chars.append(text[i + 1])
                    i += 2
                    continue
                out_chars.append(ch)
                i += 1
                continue

        # if here, we are not inside any string/triple-quote
        if ch == "#":
            # drop until newline
            # advance i to next line
            while i < n and text[i] != "\n":
                i += 1
            # keep the newline if any
            if i < n and text[i] == "\n":
                out_chars.append("\n")
                i += 1
            continue

        out_chars.append(ch)
        i += 1

    return "".join(out_chars)



def find_target_fields(parsed: Optional[dict], raw_text: str) -> Tuple[dict, dict, dict]:
    """
    Given a parsed TOML dict (or None if parsing failed) and the raw text (comments not removed),
    return per-file results:
      - fields_found: mapping field_key -> value_repr, resolved (bool), resolved_value (when parsed), urls []
      - tool_flat: flattened mapping of keys under 'tool' => tool.section.key => value_repr/urls
      - errors: dict of parsing/errors note
    If parsed is None we fall back to text-based conservative extraction (regex based) using stripped comments.
    """
    fields_found = {}
    tool_flat = {}
    errors = {}

    # For URL extraction we will prefer parsed structure; else use stripped text + regex within value snippets.

    if parsed is not None:
        # Helper to set field if value exists
        def set_field(field_key: str, value: Any):
            urls = extract_urls_from_value(value)
            fields_found[field_key] = {
                "value_repr": repr_value(value),
                "resolved": True,
                "resolved_value": value if isinstance(value, (str, int, float, list, dict, bool, type(None))) else repr(value),
                "urls": urls,
            }

        # 1) dependency-groups: top-level table or table array
        if isinstance(parsed, dict):
            # dependency-groups may be a table
            if "dependency-groups" in parsed:
                set_field("dependency-groups", parsed["dependency-groups"])

            # build-system keys
            bs = parsed.get("build-system", {})
            if isinstance(bs, dict):
                if "build-backend" in bs:
                    set_field("build-system.build-backend", bs["build-backend"])
                if "requires" in bs:
                    set_field("build-system.requires", bs["requires"])
                if "backend-path" in bs:
                    set_field("build-system.backend-path", bs["backend-path"])

            # project keys
            proj = parsed.get("project", {})
            if isinstance(proj, dict):
                for k in ("dependencies", "optional-dependencies", "scripts", "entry-points"):
                    if k in proj:
                        set_field(f"project.{k}", proj[k])

            # tool.* general extraction
            tool = parsed.get("tool", {})
            if isinstance(tool, dict):
                # flatten tool.* into tool.<section>.<key> representation
                for section, section_val in tool.items():
                    if isinstance(section_val, dict):
                        for key, val in section_val.items():
                            fk = f"tool.{section}.{key}"
                            # special-case nested dicts (e.g., tool.poetry.plugins may be nested)
                            fields_found[fk] = {
                                "value_repr": repr_value(val),
                                "resolved": True,
                                "resolved_value": val if isinstance(val, (str, int, list, dict, bool, type(None))) else repr(val),
                                "urls": extract_urls_from_value(val),
                            }
                    else:
                        # section_val is primitive
                        fk = f"tool.{section}"
                        fields_found[fk] = {
                            "value_repr": repr_value(section_val),
                            "resolved": True,
                            "resolved_value": section_val,
                            "urls": extract_urls_from_value(section_val),
                        }

            # tool.setuptools.script-files
            tool_setuptools = parsed.get("tool", {}).get("setuptools", {})
            if isinstance(tool_setuptools, dict) and "script-files" in tool_setuptools:
                set_field("tool.setuptools.script-files", tool_setuptools["script-files"])

            # tool.poetry specifics
            tool_poetry = parsed.get("tool", {}).get("poetry", {})
            if isinstance(tool_poetry, dict):
                if "dependencies" in tool_poetry:
                    set_field("tool.poetry.dependencies", tool_poetry["dependencies"])
                if "scripts" in tool_poetry:
                    set_field("tool.poetry.scripts", tool_poetry["scripts"])
                if "requires-plugins" in tool_poetry:
                    set_field("tool.poetry.requires-plugins", tool_poetry["requires-plugins"])
                # plugins: tool.poetry.plugins may be a mapping of plugin-group -> mapping
                plugins = tool_poetry.get("plugins")
                if isinstance(plugins, dict):
                    for plugin_group, plugin_val in plugins.items():
                        fk = f'tool.poetry.plugins.{plugin_group}'
                        fields_found[fk] = {
                            "value_repr": repr_value(plugin_val),
                            "resolved": True,
                            "resolved_value": plugin_val,
                            "urls": extract_urls_from_value(plugin_val),
                        }

                # poetry sources: could be array of tables at tool.poetry.source
                sources = tool_poetry.get("source")
                if isinstance(sources, list):
                    # record each url under tool.poetry.source[i].url and also aggregate under tool.poetry.source.url
                    for idx, s in enumerate(sources):
                        if isinstance(s, dict) and "url" in s:
                            fk = f"tool.poetry.source[{idx}].url"
                            set_field(fk, s["url"])
                    # also collect all urls at top-level key
                    all_src_urls = []
                    for s in sources:
                        if isinstance(s, dict) and "url" in s:
                            all_src_urls.append(s["url"])
                    if all_src_urls:
                        set_field("tool.poetry.source.url", all_src_urls)

            # project entry-points often live at project.entry-points (mapping)
            # already handled above as project.entry-points

        return fields_found, tool_flat, errors

    # parsed is None -> fallback text-based conservative extraction
    # We'll use stripped text (without comments) to locate keys and values via regex.
    try:
        stripped = strip_toml_comments(raw_text)
    except Exception:
        stripped = raw_text

    # helper regex patterns
    #  - matches table headers: [foo] or [tool.poetry]
    table_re = re.compile(r'^\s*\[([^\]]+)\]\s*$', re.M)
    array_table_re = re.compile(r'^\s*\[\[([^\]]+)\]\]\s*$', re.M)

    # find occurrence of target headers/keys in text, extract rough values
    # For simple keys like build-backend = "..." we search for ^key\s*=\s*(value)
    def find_key_value(key_full: str) -> List[str]:
        # naive pattern: key possibly after table header
        regex = re.compile(r'^\s*' + re.escape(key_full) + r'\s*=\s*(.+)$', re.M)
        vals = []
        for m in regex.finditer(stripped):
            valraw = m.group(1).strip()
            # trim trailing commas if present
            if valraw.endswith(","):
                valraw = valraw[:-1].rstrip()
            vals.append(valraw)
        return vals

    # gather a few keys:
    # build-system keys
    for key in ("build-backend", "requires", "backend-path"):
        vals = find_key_value(key)
        if vals:
            fields_found[f"build-system.{key}"] = {
                "value_repr": json.dumps(vals, ensure_ascii=False),
                "resolved": False,
                "resolved_value": None,
                "urls": list({u for v in vals for u in URL_RE.findall(v)}),
            }

    # dependency-groups: presence of table header [dependency-groups] or [dependency-groups.*]
    if re.search(r'^\s*\[dependency-groups[^\]]*\]', stripped, re.M):
        fields_found["dependency-groups"] = {
            "value_repr": "<table present>",
            "resolved": False,
            "resolved_value": None,
            "urls": [],
        }

    # project.* keys
    for projk in ("dependencies", "optional-dependencies", "scripts", "entry-points"):
        # we search for lines like 'dependencies = [' or under [project] table we find key
        # find occurrences of 'project.' prefix or "[project]" header and subsequent key lines
        vals = find_key_value(projk)
        if vals:
            fields_found[f"project.{projk}"] = {
                "value_repr": json.dumps(vals, ensure_ascii=False),
                "resolved": False,
                "resolved_value": None,
                "urls": list({u for v in vals for u in URL_RE.findall(v)}),
            }
        else:
            # try to find under [project] section: simple: locate '[project]' and read next 10 lines for the key
            m = re.search(r'^\s*\[project\]\s*$', stripped, re.M)
            if m:
                start = m.end()
                block = stripped[start:start + 1000]  # small window
                m2 = re.search(r'^\s*' + re.escape(projk) + r'\s*=\s*(.+)$', block, re.M)
                if m2:
                    v = m2.group(1).strip().rstrip(',')
                    fields_found[f"project.{projk}"] = {
                        "value_repr": v,
                        "resolved": False,
                        "resolved_value": None,
                        "urls": URL_RE.findall(v),
                    }

    # tool.* fallback: find any table header starting with tool.
    for m in table_re.finditer(stripped):
        tname = m.group(1).strip()
        if tname.startswith("tool."):
            # naive capture: we will collect the following 200 chars as the value snippet
            start = m.end()
            snippet = stripped[start:start + 400]
            fields_found[f"table.{tname}"] = {
                "value_repr": snippet.strip()[:400],
                "resolved": False,
                "resolved_value": None,
                "urls": URL_RE.findall(snippet),
            }

    # tool.poetry.source array table
    for m in array_table_re.finditer(stripped):
        tname = m.group(1).strip()
        if tname == "tool.poetry.source":
            # get snippet and extract url= occurrences
            start = m.end()
            snippet = stripped[start:start + 400]
            urls = URL_RE.findall(snippet)
            fields_found["tool.poetry.source.url"] = {
                "value_repr": snippet.strip()[:400],
                "resolved": False,
                "resolved_value": None,
                "urls": urls,
            }

    return fields_found, tool_flat, errors


def process_file(path: Path) -> Tuple[Optional[dict], Optional[str]]:
    """
    Process a single TOML file. Returns (per_file_result, status_message)
    per_file_result is a dict containing:
      - fields: mapping field_key -> {value_repr, resolved, resolved_value, urls}
      - tool_entries: mapping for tool.* flattened
    status_message indicates parse backend or error string for console printing.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        return None, f"read_error: {e}"

    # remove BOM if present
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")

    # parse if possible
    parsed, backend = safe_parse_toml(raw)
    if parsed is not None:
        fields_found, tool_flat, errors = find_target_fields(parsed, raw)
        status = f"parsed_with:{backend}"
    else:
        # fallback to text-based conservative extraction using stripped comments
        fields_found, tool_flat, errors = find_target_fields(None, raw)
        status = "fallback_text"

    per_file = {"fields": fields_found, "tool_flat": tool_flat}
    return per_file, status

def aggregate_directory(toml_dir):
    root = toml_dir.resolve()
    toml_paths = list(root.rglob("*.toml"))
    total = len(toml_paths)
    print(f"Found {total} .toml files under {root}")
    
    # initialize global aggregations
    field_counts = Counter()
    field_files = defaultdict(list)  # field -> list of files
    url_sources_by_field = defaultdict(lambda: defaultdict(set))  # field -> url -> set(files)
    file_details = {}
    tool_field_counts = Counter()
    tool_field_files = defaultdict(list)
    
    file_index = 0
    for p in toml_paths:
        file_index += 1
        print(f"[{file_index}/{total}] Processing {p} ...", end=" ")
        per_file, status = process_file(p)
        if per_file is None:
            print(status)
            continue
        print(status)

        fields = per_file.get("fields", {})
        tool_flat = per_file.get("tool_flat", {})

        # record file-level details
        file_key = str(p)
        file_details[file_key] = {"fields": {}, "tool_flat": {}}

        # update field_counts and per-file values
        for fk, info in fields.items():
            # treat presence count once per file
            field_counts[fk] += 1
            field_files[fk].append(file_key)

            # record value + urls
            urls = info.get("urls", [])
            # dedupe urls for this file/field
            unique_urls = list(dict.fromkeys(urls))
            file_details[file_key]["fields"][fk] = {
                "value_repr": info.get("value_repr"),
                "resolved": bool(info.get("resolved", False)),
                "resolved_value": info.get("resolved_value"),
                "urls": unique_urls,
            }
            for u in unique_urls:
                url_sources_by_field[fk][u].add(file_key)

        # flatten tool.* (if present)
        for tfk, tinfo in tool_flat.items():
            tool_field_counts[tfk] += 1
            tool_field_files[tfk].append(file_key)
            file_details[file_key]["tool_flat"][tfk] = tinfo

    # Build serializable url counters
    url_counter_by_field = {
        fk: {u: len(srcs) for u, srcs in urlmap.items()} for fk, urlmap in url_sources_by_field.items()
    }
    url_sources_serial = {
        fk: {u: sorted(list(srcs)) for u, srcs in urlmap.items()} for fk, urlmap in url_sources_by_field.items()
    }

    result = {
        "scan_root": str(root),
        "parser_backend": parse_backend,
        "summary": {
            "total_toml_files": total,
            "total_files_processed": file_index,
        },
        "field_counts": dict(field_counts),
        "field_files": dict(field_files),
        "url_counter_by_field": url_counter_by_field,
        "url_sources_by_field": url_sources_serial,
        "tool_field_counts": dict(tool_field_counts),
        "tool_field_files": dict(tool_field_files),
        "files": file_details,
    }

    return result


if __name__ == "__main__":
    result = aggregate_directory(Path("/home/hello/finder/ConfigScoper/BigQueryData/configFiles/pyproject"))

    outp = Path("/home/hello/finder/ConfigScoper/parser/parseToml/output/toml_statistic.json")
    outp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote JSON result to", outp.resolve())

