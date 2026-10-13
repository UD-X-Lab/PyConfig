import json
import os
import shlex
from pathlib import Path
from collections import defaultdict


def normalize_cmd(value: str) -> str:
  if "/" in value:
    return Path(value).name
  return value


def get_experiment_results(input_path):
  input_data = json.load(input_path.open("r", encoding="utf-8"))

  matched_console_cmds = defaultdict(list)
  for filepath, info in input_data["files"].items():
    resolved_value = info["resolved_value"]
    if not resolved_value:
      continue

    if "console_scripts" not in resolved_value:
      continue

    console_scripts = resolved_value["console_scripts"]

    for cmd in console_scripts.keys():
      if not isinstance(cmd, str):
        continue

      # print(cmd)
      status = os.system(f"which {cmd}")
      if status == 0: # command exists
        if filepath not in matched_console_cmds[cmd]:
          matched_console_cmds[cmd].append(filepath)



  # entries = payload.get("project.entry-points")
  # if not isinstance(entries, list):
  #   return

  # found_cmds = {}
  # for entry in entries:
  #   if not isinstance(entry, dict):
  #     continue
  #   value = entry.get("value")
  #   if not isinstance(value, dict):
  #     continue
  #   console_scripts = value.get("console_scripts")
  #   if not isinstance(console_scripts, dict):
  #     continue
  

  output_path = base_dir / "found_console_scripts_cmds.json"
  with output_path.open("w", encoding="utf-8") as f:
    json.dump(found_cmds, f, indent=2, ensure_ascii=True, sort_keys=True)


def main():
  dataset = [f for f in Path("data").rglob("*.json")]
  for datafile in dataset:
    get_experiment_results(datafile)

if __name__ == "__main__":
  main()
