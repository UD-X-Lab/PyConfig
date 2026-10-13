from pathlib import Path
import ast, tokenize, json, re, argparse
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from tqdm import tqdm

TARGET_FIELDS = {
    "install_requires",
    "dependency_links",
    "tests_require",
    "extras_require",
    "distclass",
    "test_suite",
    "cmdclass",
    "test_loader",
    "test_runner",
    "scripts",
    "ext_modules",
    "ext_package",
}

URL_RE = re.compile(r"[A-Za-z0-9+\-_.]+://[^\s'\"),\]]+")

def collect_string_literals(node: ast.AST) -> List[str]:
    """Walk an AST node and collect all literal strings inside (best-effort)."""
    strs: List[str] = []
    for n in ast.walk(node):
        # ast.Constant in Python 3.8+; ast.Str for older
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            strs.append(n.value)
        elif isinstance(n, ast.Str):
            strs.append(n.s)
    # preserve order, dedupe
    return list(dict.fromkeys(strs))

def safe_literal_eval(node: ast.AST, assigns: Dict[str, Any]) -> Tuple[Optional[Any], bool]:
    """Try ast.literal_eval, fall back to resolving top-level literal assignment names."""
    try:
        val = ast.literal_eval(node)
        return val, True
    except Exception:
        # If node is a Name referencing a top-level literal assignment, return it
        if isinstance(node, ast.Name):
            if node.id in assigns:
                return assigns[node.id], True
        # attribute like CONST.X or X.Y (best-effort)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.attr in assigns:
                return assigns[node.attr], True
            if node.value.id in assigns:
                return assigns[node.value.id], True
    return None, False

def extract_urls_from_obj(obj: Any) -> List[str]:
    """Extract URLs from a Python literal object (list/dict/str)."""
    urls: List[str] = []
    if isinstance(obj, str):
        urls.extend(URL_RE.findall(obj))
    elif isinstance(obj, (list, tuple, set)):
        for elt in obj:
            urls.extend(extract_urls_from_obj(elt))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            urls.extend(extract_urls_from_obj(k))
            urls.extend(extract_urls_from_obj(v))
    return list(dict.fromkeys(urls))

def node_value_repr_and_urls(node: ast.AST, source: str,
                             top_assigns: Dict[str, Any],
                             top_strings: Dict[str, List[str]],
                             alias_map: Dict[str, str]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Resolve node to a representation and extract URLs:
     - try literal eval -> resolved_value, urls from that
     - else collect literal strings inside node -> urls from them
     - else if node is a Name, follow alias chain to find top_strings or top_assigns
    Returns (value_info_dict, urls_list)
    value_info_dict = {"value_repr": str, "resolved": bool, "resolved_value": maybe}
    """
    # 1) literal eval attempt
    val, ok = safe_literal_eval(node, top_assigns)
    if ok:
        # resolved_value: try to keep JSON-serializable otherwise use repr
        try:
            json.dumps(val)
            resolved_value = val
        except Exception:
            resolved_value = repr(val)
        try:
            value_repr = json.dumps(val, ensure_ascii=False)
        except Exception:
            value_repr = repr(val)
        urls = extract_urls_from_obj(val)
        return ({"value_repr": value_repr, "resolved": True, "resolved_value": resolved_value}, urls)

    # 2) collect string literals inside node
    strings = collect_string_literals(node)
    urls: List[str] = []
    for s in strings:
        urls.extend(URL_RE.findall(s))

    # 3) if node is a Name, follow alias chain to find assigned strings or literal values
    if isinstance(node, ast.Name):
        visited = set()
        name = node.id
        while True:
            if name in visited:
                break
            visited.add(name)
            # direct top_assigns value (maybe partially resolved)
            if name in top_assigns:
                val = top_assigns[name]
                try:
                    json.dumps(val)
                    resolved_value = val
                except Exception:
                    resolved_value = repr(val)
                # value_repr: try JSON
                try:
                    value_repr = json.dumps(val, ensure_ascii=False)
                except Exception:
                    value_repr = repr(val)
                urls = extract_urls_from_obj(val)
                return ({"value_repr": value_repr, "resolved": True, "resolved_value": resolved_value}, urls)
            # top_strings for this name
            if name in top_strings and top_strings[name]:
                # use collected strings
                strs = top_strings[name]
                urls = []
                for s in strs:
                    urls.extend(URL_RE.findall(s))
                # value_repr: show concatenated literals snippet
                return ({"value_repr": json.dumps(strs, ensure_ascii=False), "resolved": False, "resolved_value": None}, list(dict.fromkeys(urls)))
            # follow alias (e.g., TESTS_REQUIRE = INSTALL_REQUIRES)
            if name in alias_map:
                name = alias_map[name]
                continue
            break

    # 4) fallback: try to get source segment for value_repr
    seg = None
    try:
        seg = ast.get_source_segment(source, node)
    except Exception:
        seg = None
    if seg:
        return ({"value_repr": seg.strip(), "resolved": False, "resolved_value": None}, list(dict.fromkeys(urls)))
    # final fallback
    try:
        dump = ast.dump(node)
    except Exception:
        dump = "<unrepresentable>"
    return ({"value_repr": dump, "resolved": False, "resolved_value": None}, list(dict.fromkeys(urls)))



def analyze_setup_in_source(source: str) -> Tuple[Set[str], Dict[str, Dict[str, Any]], Dict[str, Set[str]]]:
    """
    Returns:
      - fields_found: set of field keys (e.g., 'install_requires', 'extras_require.dev', ...)
      - field_values: mapping field_key -> value_info dict
      - field_urls_per_file: mapping field_key -> set(urls) (file-level de-duped)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set(), {}, {}

    # gather top-level assigns: literal eval where possible, collect strings inside otherwise, and alias mapping
    top_assigns: Dict[str, Any] = {}
    top_strings: Dict[str, List[str]] = {}   # name -> list of literal strings found inside the RHS AST
    alias_map: Dict[str, str] = {}           # name -> other name (for TESTS_REQUIRE = INSTALL_REQUIRES)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            # we only handle simple NAME = expr (skip tuple targets etc)
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name = t.id
                    # try literal eval
                    try:
                        val = ast.literal_eval(node.value)
                        top_assigns[name] = val
                    except Exception:
                        # collect string literals inside RHS
                        strs = collect_string_literals(node.value)
                        if strs:
                            top_strings[name] = strs
                        # alias: RHS is a Name
                        if isinstance(node.value, ast.Name):
                            alias_map[name] = node.value.id
                        # also if RHS is a Name.attribute or similar, we could record alias to its id.attr? skip for now

    fields_found: Set[str] = set()
    field_values: Dict[str, Dict[str, Any]] = {}
    field_urls_per_file: Dict[str, Set[str]] = defaultdict(set)

    # find setup(...) calls
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        fname = None
        if isinstance(func, ast.Name):
            fname = func.id
        elif isinstance(func, ast.Attribute):
            fname = func.attr
        if fname != "setup":
            continue

        for kw in node.keywords:
            key = kw.arg
            if not key:
                continue
            # treat extras_require specially later
            if key not in TARGET_FIELDS and key != "extras_require":
                continue

            # mark presence
            # for extras we still use top-level key 'extras_require'
            if key == "extras_require":
                fields_found.add("extras_require")
            else:
                fields_found.add(key)

            # if not already recorded for this file, record value_repr/resolved etc
            field_key_to_record = key  # may be superseded for extras extras
            if field_key_to_record not in field_values:
                valinfo, urls = node_value_repr_and_urls(kw.value, source, top_assigns, top_strings, alias_map)
                field_values[field_key_to_record] = valinfo
                # record urls for this key
                for u in urls:
                    field_urls_per_file[field_key_to_record].add(u)

                # if extras_require resolved to a dict, create extras_require.<name> entries
                # check whether we got a resolved value
                if valinfo.get("resolved"):
                    resolved_val = valinfo.get("resolved_value")
                    if isinstance(resolved_val, dict):
                        # resolved extras_require dict: record each extra
                        for extra_name, v in resolved_val.items():
                            fk = f"extras_require.{extra_name}"
                            fields_found.add(fk)
                            # value representation for the extra
                            try:
                                json.dumps(v)
                                rv = v
                            except Exception:
                                rv = repr(v)
                            try:
                                repr_str = json.dumps(v, ensure_ascii=False)
                            except Exception:
                                repr_str = repr(v)
                            if fk not in field_values:
                                field_values[fk] = {"value_repr": repr_str, "resolved": True, "resolved_value": rv}
                            # extract urls from the extra value
                            extr_urls = extract_urls_from_obj(v)
                            for u in extr_urls:
                                field_urls_per_file[fk].add(u)
                else:
                    # not resolved; but maybe we collected strings for the RHS or alias chain,
                    # node_value_repr_and_urls already handled alias chain and returned urls if any
                    pass

    return fields_found, field_values, field_urls_per_file


def aggregate(root: Path) -> Dict[str, Any]:
    root = Path(root)
    field_counts = Counter()
    field_files: Dict[str, Set[str]] = defaultdict(set)
    files_detail: Dict[str, Dict[str, Any]] = {}
    url_sources_by_field: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    
    sum_files = list(root.rglob("*.py"))
    
    # for p in root.rglob("*.py"):
    for p in tqdm(sum_files):
        try:
            with tokenize.open(p) as fh:
                src = fh.read()
        except Exception:
            continue

        if "setup(" not in src:
            continue
        
        print(f"Analyzing {str(p)}")
        fields_found, field_values, field_urls_per_file = analyze_setup_in_source(src)
        if not fields_found and not field_values:
            continue

        file_key = str(p)
        files_detail[file_key] = {"fields": {}}

        for f in fields_found:
            field_counts[f] += 1
            field_files[f].add(file_key)

        # attach values and urls
        for fk, info in field_values.items():
            files_detail[file_key]["fields"][fk] = {
                "value_repr": info.get("value_repr"),
                "resolved": bool(info.get("resolved", False)),
                "resolved_value": info.get("resolved_value", None),
                "urls": sorted(list(field_urls_per_file.get(fk, set()))),
            }
            # aggregate url sources
            for u in field_urls_per_file.get(fk, set()):
                url_sources_by_field[fk][u].add(file_key)

        # ensure field keys that had only urls (maybe from extras unresolved) are present
        for fk, urls in field_urls_per_file.items():
            if fk not in files_detail[file_key]["fields"]:
                files_detail[file_key]["fields"][fk] = {
                    "value_repr": None,
                    "resolved": False,
                    "resolved_value": None,
                    "urls": sorted(list(urls))
                }
            for u in urls:
                url_sources_by_field[fk][u].add(file_key)

    # build url_counter_by_field
    url_counter_by_field = {fk: {u: len(srcs) for u, srcs in urlmap.items()} for fk, urlmap in url_sources_by_field.items()}
    serial_field_files = {k: sorted(list(v)) for k, v in field_files.items()}

    return {
        "field_counts": dict(field_counts),
        "field_files": serial_field_files,
        "files": files_detail,
        "url_counter_by_field": url_counter_by_field,
        "url_sources_by_field": {fk: {u: sorted(list(srcs)) for u, srcs in urlmap.items()} for fk, urlmap in url_sources_by_field.items()}
    }

def main():
    root = Path("/home/hello/finder/ConfigScoper/BigQueryData/configFiles/setup")

    outp = Path("/home/hello/finder/ConfigScoper/parser/parseSetup/output/setup_statistic.json")

    stats = aggregate(root)
    with outp.open("w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)
    print("Wrote", outp.resolve())

if __name__ == "__main__":
    main()