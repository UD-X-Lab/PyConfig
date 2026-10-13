from __future__ import annotations

"""
Extract the top-level \"files\" field from the massive
data/links/github_hijack_account/pyproject/toml_field_stats.json
into data/links/domain_takeover/pyproject/files.json using
streaming to avoid loading the ~870MB source into memory.
"""

from pathlib import Path


SRC = Path("data/links/github_hijack_account/pyproject/toml_field_stats.json")
DST = Path("data/links/domain_takeover/pyproject/files.json")


def extract_files_field(src: Path = SRC, dst: Path = DST, chunk_size: int = 1 << 20) -> None:
    target_key = "files"
    # States: search -> to_value (waiting for first non-space after colon)
    # -> capture (stream the object that is the value of "files")
    state = "search"
    in_string = False
    escape = False
    brace_depth = 0  # track nesting at top-level to ensure we only grab the root "files"
    current_string: list[str] = []  # collect characters while inside a string
    pending_key = False  # True when we just closed a string equal to target_key at depth 1

    # Capture state
    capture_in_string = False
    capture_escape = False
    capture_depth = 0

    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("r", encoding="utf-8") as f, dst.open("w", encoding="utf-8") as out:
        out.write('{"files": ')

        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            i = 0
            chunk_len = len(chunk)

            while i < chunk_len:
                ch = chunk[i]

                if state == "to_value":
                    if ch.isspace():
                        i += 1
                        continue
                    state = "capture"
                    capture_in_string = False
                    capture_escape = False
                    capture_depth = 0
                    # Re-process this character under capture rules

                if state == "capture":
                    out.write(ch)

                    if capture_escape:
                        capture_escape = False
                    elif ch == "\\" and capture_in_string:
                        capture_escape = True
                    elif ch == '"':
                        capture_in_string = not capture_in_string

                    if not capture_in_string:
                        if ch == "{":
                            capture_depth += 1
                        elif ch == "}":
                            capture_depth -= 1
                            if capture_depth == 0:
                                out.write("\n}")
                                return

                    i += 1
                    continue

                # State == "search"
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                        string_value = "".join(current_string)
                        current_string.clear()
                        if (
                            brace_depth == 1
                            and string_value == target_key
                        ):
                            pending_key = True
                    else:
                        current_string.append(ch)
                else:
                    if ch == '"':
                        in_string = True
                        escape = False
                        current_string.clear()
                    else:
                        if ch == "{":
                            brace_depth += 1
                        elif ch == "}":
                            brace_depth -= 1

                        if pending_key:
                            if ch.isspace():
                                pass
                            elif ch == ":":
                                state = "to_value"
                                pending_key = False
                            else:
                                pending_key = False

                i += 1

    raise RuntimeError('Could not find top-level "files" field in the source JSON.')


if __name__ == "__main__":
    extract_files_field()
