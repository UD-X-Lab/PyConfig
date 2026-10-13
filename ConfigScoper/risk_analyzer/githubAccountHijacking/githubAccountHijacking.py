from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TypeVar, Callable
from urllib import error, request
from urllib.parse import urlparse
import socket

T = TypeVar("T")


VCS_PREFIX_PATTERN = re.compile(r"^(?P<vcs>[a-z0-9]+)\+(?P<body>.+)$", flags=re.IGNORECASE)


def iter_github_lines(url) -> Iterable[str]:
    if "github" in url:
        return url

def strip_fragment(url: str) -> str:
    return url.split("#", 1)[0].strip()

def build_https_from_rest(rest: str) -> str:
    """Convert host/path portions that may still contain git@ or colon separators."""
    cleaned = rest.strip().lstrip("/")
    if cleaned.startswith("git@"):
        cleaned = cleaned.split("@", 1)[1]

    if cleaned.startswith("github.com:"):
        cleaned = cleaned.replace("github.com:", "github.com/", 1)
    elif cleaned.startswith("github.com;"):
        cleaned = cleaned.replace("github.com;", "github.com/", 1)

    if cleaned.startswith("github.com"):
        cleaned = cleaned[len("github.com") :].lstrip("/")
        host = "github.com"
    else:
        host = cleaned.split("/", 1)[0]
        cleaned = cleaned[len(host) :].lstrip("/")
        if host != "github.com":
            return f"https://{host}{('/' + cleaned) if cleaned else ''}"

    return f"https://{host}{('/' + cleaned) if cleaned else '/'}"

def normalize_url(raw_url: str) -> str:
    if raw_url is None:
        return
    url = strip_fragment(raw_url)
    if not url:
        return ""

    match = VCS_PREFIX_PATTERN.match(url)
    body = match.group("body") if match else url

    normalized = body
    lower_body = body.lower()

    if lower_body.startswith(("https://", "http://")):
        normalized = body
    elif lower_body.startswith(("git://", "ssh://")):
        _, rest = body.split("://", 1)
        normalized = build_https_from_rest(rest)

    elif lower_body.startswith("git@github.com"):
        normalized = build_https_from_rest(body)
    elif lower_body.startswith("github.com"):
        normalized = build_https_from_rest(body)
    else:
        normalized = body

    # Handle git+https or git+http cases.
    if match:
        scheme_part = body.split("://", 1)[0].lower() if "://" in body else ""
        if scheme_part in {"https", "http"}:
            normalized = body
        elif scheme_part in {"git", "ssh"}:
            rest = body.split("://", 1)[1] if "://" in body else body
            normalized = build_https_from_rest(rest)

    normalized = normalized.strip()

    # Final cleanup for lingering git@ forms.
    if normalized.lower().startswith("https://git@github.com"):
        normalized = build_https_from_rest(normalized[len("https://") :])
    if normalized.lower().startswith("http://git@github.com"):
        normalized = build_https_from_rest(normalized[len("http://") :])

    if normalized.lower().startswith("git://github.com"):
        normalized = build_https_from_rest(normalized[len("git://") :])
    if normalized.lower().startswith("ssh://git@github.com"):
        normalized = build_https_from_rest(normalized[len("ssh://") :])

    # Ensure we prefer https for GitHub.
    parsed = urlparse(normalized)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower().endswith("github.com"):
        normalized_path = parsed.path if parsed.path else "/"
        normalized = f"https://github.com{normalized_path}"
        if parsed.query:
            normalized += f"?{parsed.query}"

    return normalized

def extract_author(normalized_url: str) -> Optional[str]:
    if normalized_url is None:
        return
    parsed = urlparse(normalized_url)
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [segment for segment in parsed.path.split("/") if segment]
    return parts[0] if parts else None

def author_exists(author: Optional[str], cache: Dict[str, Optional[bool]]) -> Optional[bool]:
    if not author:
        return None
    if author in cache:
        return cache[author]

    profile_url = f"https://github.com/{author}"
    req = request.Request(profile_url, headers={"User-Agent": "github-url-checker"})

    try:
        with request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                cache[author] = True
    except socket.timeout:
        cache[author] = None
    except error.HTTPError as http_err:
        if http_err.code == 404:
            cache[author] = False
        else:
            cache[author] = None
    except error.URLError:
        cache[author] = None

    return cache[author]

def writeJson(out_path, results):
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def urlFilter(url):
    if not url:
        return url
    cleaned = url.split("#", 1)[0].strip()
    if not cleaned:
        return cleaned

    if "@" not in cleaned:
        return cleaned

    if cleaned.startswith("git@") and "://" not in cleaned:
        if ":" in cleaned:
            prefix, rest = cleaned.split(":", 1)
            if "@" in rest:
                rest = rest.split("@", 1)[0]
                return f"{prefix}:{rest}"
        return cleaned

    if "://" in cleaned:
        scheme, rest = cleaned.split("://", 1)
        host_part = rest.split("/", 1)[0]
        if "@" in host_part:
            if "/" in rest:
                path = rest.split("/", 1)[1]
                if "@" in path:
                    path = path.split("@", 1)[0]
                    return f"{scheme}://{host_part}/{path}"
            return f"{scheme}://{rest}"
        return f"{scheme}://{rest.split('@', 1)[0]}"

    return cleaned.split("@", 1)[0]

def urlAliveStatus(url):
    if not url:
        return {"alive": False, "status": "empty"}

    try:
        req = request.Request(url, headers={"User-Agent": "url-alive-checker"})
        with request.urlopen(req, timeout=5) as resp:
            return {"alive": True, "status": resp.status}
    except error.HTTPError as http_err:
        if http_err.code == 404:
            return {"alive": False, "status": 404}
        return {"alive": False, "status": http_err.code}
    except Exception:
        return {"alive": False, "status": "error"}

def gAHijacking(urls, cache: Dict[str, Optional[bool]]) -> List[dict]:
    results: List[dict] = []
    print(len(urls))

    for url in urls:
        github_url = iter_github_lines(url)
        normalized = normalize_url(github_url)
        filteredURL = urlFilter(normalized)
        print(f"Original URL: {url}, filtered URL: {filteredURL}")
        # urlStatus = urlAliveStatus(filteredURL)
        # if urlStatus["alive"] == True:
        #     continue
        author = extract_author(filteredURL)
        exists = author_exists(author, cache)
        if exists == False:
            results.append(
                {
                    "original_url": url,
                    "normalized_url": filteredURL or None,
                    "author": author,
                    "author_exists": exists,
                    # "url_status": False
                }
            )

    return results

def urlFromPipfileOrLock(data, output):
    all_urls = list() 
    for filepath, info in data["files"].items():
        urls = info["urls"]
        if not urls:
            continue

        all_urls += urls

    print(f"Found {len(all_urls)} unique urls")

    cache: Dict[str, Optional[bool]] = {}
    reqResult = gAHijacking(all_urls, cache)
    reqIRLInfo = dict()
    reqIRLInfo["total_urls"] = len(urls)
    reqIRLInfo["githubHijackNum"] = len(reqResult)
    reqIRLInfo["Result"] = reqResult
    
    writeJson(output, reqResult)


def urlFromReq(data, output):
    urls = []
    for url, num in data.items():
        urls.append(url)
    cache: Dict[str, Optional[bool]] = {}
    reqResult = gAHijacking(urls, cache)
    reqIRLInfo = dict()
    reqIRLInfo["total_urls"] = len(urls)
    reqIRLInfo["githubHijackNum"] = len(reqResult)
    reqIRLInfo["Result"] = reqResult
    
    writeJson(output, reqResult)

def urlFromToml(data, output):
    urls = []
    for key,value in data.items():
        if key == "files":
            for file, fieldInfo in value.items():
                if fieldInfo.get("urls"):
                    urls.append(fieldInfo.get("urls"))
    cache: Dict[str, Optional[bool]] = {}
    tomlResult = gAHijacking(urls, cache)
    tomlInfo = dict()
    tomlInfo["total_urls"] = len(urls)
    tomlInfo["githubHijackNum"] = len(tomlResult)
    tomlInfo["Result"] = tomlResult
    
    writeJson(output, tomlResult)

def urlFromSetup(data, json_path, output):
    urls = []
    for key,value in data.items():
        if key == "files":
            for file, fieldInfo in value.items():
                if fieldInfo.get("urls"):
                    urls.append(fieldInfo.get("urls"))
    cache: Dict[str, Optional[bool]] = {}
    tomlResult = gAHijacking(urls, cache)
    tomlInfo = dict()
    tomlInfo["total_urls"] = len(urls)
    tomlInfo["githubHijackNum"] = len(tomlResult)
    tomlInfo["Result"] = tomlResult
    
    writeJson(output, tomlResult)

def extractURLInField(input_dir, task) -> None:

  for json_path in input_dir.rglob("*.json"):
    with open(json_path) as f:
      input_data = json.load(f)

    if json_path.parent.name in ["extrasRequire", "develop", "default"]:
      output = Path(f"output/{task}") / json_path.parent.name /  json_path.name
    else:
      output = Path(f"output/{task}") / json_path.name

    output.parent.mkdir(parents=True, exist_ok=True)

    if task in ["parsePipfile",  "parsePipfileLock", "parseSetup"]:
      urlFromPipfileOrLock(input_data, output)
    elif task == "parseReq":
      urlFromReq(input_data, output)
    elif task == "parseToml":
      urlFromToml(input_data, output)



    # for risk_dir in parser_root.rglob("R2"):
    #     if not risk_dir.is_dir():
    #         continue
    #     for json_path in risk_dir.rglob("*.json"):
    #         try:
    #             data = json.loads(json_path.read_text(encoding="utf-8"))
    #         except Exception:
    #             continue
    #         urls = _extract_urls(data)
    #         if not urls:
    #             continue
    #         results.append(
    #             {
    #                 "source_json": str(json_path),
    #                 "urls": urls,
    #             }
    #         )

    # with output_path.open("w", encoding="utf-8") as f:
    #     json.dump(results, f, ensure_ascii=False, indent=2)

def main():
  tasks = ["parsePipfileLock", "parsePipfile", "parseReq", "parseSetup", "parseToml"]
  for task in tasks: 
    input_dir = Path(f"parser/{task}/output/fieldInfo/R1")
    extractURLInField(input_dir, task)

if __name__ == "__main__":
  main()
