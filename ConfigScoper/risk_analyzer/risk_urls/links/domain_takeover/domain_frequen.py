from pathlib import Path
import re

base = Path("data/links/domain_takeover")
domains = [d.strip().lower() for d in (base / "takeover_domains").read_text().splitlines() if d.strip()]

dead_files = {
    "pipfile": base / "pipfile" / "dead_urls.txt",
    "pyproject": base / "pyproject" / "dead_urls.txt",
    "requirements": base / "requirements" / "dead_urls.txt",
    "setup": base / "setup" / "dead_urls.txt",
}

contents = {name: path.read_text(errors="ignore").lower() for name, path in dead_files.items()}

counts = {name: {} for name in dead_files}
for domain in domains:
    pat = re.escape(domain)
    for name, text in contents.items():
        counts[name][domain] = len(re.findall(pat, text))

total_counts = {}
for domain in domains:
    total_counts[domain] = sum(counts[name].get(domain, 0) for name in dead_files)

for name in dead_files:
    print(f"--- {name} ---")
    total = 0
    for d, c in sorted(
        ((d, c) for d, c in counts[name].items() if c),
        key=lambda x: (-x[1], x[0]),
    ):
        print(f"{d}: {c}")
        total += c
    print(total)
    print()

