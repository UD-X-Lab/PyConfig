from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TypeVar, Callable
from collections import defaultdict

def writeJson(out_path, results):
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def urlFromPipfileOrLock(data, output, write=True):
    statistics = defaultdict(int)
    for filepath, info in data["files"].items():
        urls = info["urls"]
        if not urls:
            continue

        for url in urls:
            statistics[url] += 1

    if write:
        writeJson(output, statistics)

    return statistics


def urlFromReq(data, output, write=True):
    urls = []
    statistics = defaultdict(int)
    for url, num in data.items():
        urls.append(url)
        statistics[url] = num
    
    if write:
        writeJson(output, statistics)

def urlFromToml(data, output, write=True):
    statistics = defaultdict(int)
    for key,value in data.items():
        if key == "files":
            for file, fieldInfo in value.items():
                if fieldInfo.get("urls"):
                    urls = fieldInfo.get("urls")
                    for url in urls:            
                       statistics[url] += 1
    
    if write:
        writeJson(output, statistics)
    
    return statistics

def urlFromSetup(data, output, write=True):
    statistics = defaultdict(int)
    for key,value in data.items():
        if key == "files":
            for file, fieldInfo in value.items():
                if fieldInfo.get("urls"):
                    url = fieldInfo.get("urls")
                    statistics[url] += 1
    
    if write:
        writeJson(output, statistics)

    return statistics

def get_field_statistics(input_dir, task):

  for json_path in input_dir.glob("*.json"):
    print(json_path)
    with open(json_path) as f:
      input_data = json.load(f)

    output = Path(f"stats-output/{task}") / json_path.name
    output.parent.mkdir(parents=True, exist_ok=True)

    if task in ["parsePipfile",  "parsePipfileLock", "parseSetup"]:
      urlFromPipfileOrLock(input_data, output)
    # elif task == "parseReq":
    #   urlFromReq(input_data, output)
    elif task == "parseToml":
      urlFromToml(input_data, output)

def get_field_statistics_merge(input_dir, task):
  print(input_dir)
  output = Path(f"stats-output/{task}") / (input_dir.name + ".json")
  output.parent.mkdir(parents=True, exist_ok=True)

  merged_stats = defaultdict(int)
  for json_path in input_dir.glob("*.json"):
    print(json_path)
    with open(json_path) as f:
      input_data = json.load(f)

    if task in ["parsePipfile",  "parsePipfileLock", "parseSetup"]:
      single_stat = urlFromPipfileOrLock(input_data, output, write=False)

      for url, count in single_stat.items():
        merged_stats[url] = merged_stats[url] + count

  writeJson(output, merged_stats)


def main():
  tasks = ["parsePipfileLock", "parsePipfile", "parseSetup", "parseToml"]
  for task in tasks: 
    input_dir = Path(f"parser/{task}/output/fieldInfo/R1")
    get_field_statistics(input_dir, task)

  input_dir = Path("parser/parsePipfileLock/output/fieldInfo/R1/develop")
  task = "parsePipfileLock"
  get_field_statistics_merge(input_dir, task)

  input_dir = Path("parser/parsePipfileLock/output/fieldInfo/R1/default")
  task = "parsePipfileLock"
  get_field_statistics_merge(input_dir, task)

  input_dir = Path("parser/parseSetup/output/fieldInfo/R1/extrasRequire")
  task = "parseSetup"
  get_field_statistics_merge(input_dir, task)

if __name__ == "__main__":
  main()
