from pathlib import Path
from tqdm import tqdm
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

def request_download_url(download_url, config_file):
    result = requests.get(download_url)
    if result.status_code == 200:
        with open(config_file, "w") as f:
            f.write(f"#{download_url}")
            f.write("\n")
            f.write(result.text) 

def hash_fnv1a_32(s):
    hash = 0x811c9dc5
    for x in s:
        hash = ((ord(x) ^ hash) * 0x01000193) & 0xFFFFFFFF
    return hash

def load_cfg_info(cfgBigQueryData):
    with open(cfgBigQueryData, "r") as f:
        analyze_repo_list = []
        for line in f:
            if line.strip():
                analyze_repo_list.append(json.loads(line))
        return analyze_repo_list

def get_cfg_from_bigQuery(cfgBigQueryData, outputCfgFiles, cfg):
    analyze_repo_list = load_cfg_info(cfgBigQueryData)

    with open(cfgBigQueryData, "r") as fp:
        for repo in tqdm(analyze_repo_list):
            hash_value = hash_fnv1a_32(repo["repo_name"])
            hash_value = f"{hash_value:08x}"
            
            if cfg == "setup":
                fpath = outputCfgFiles / f"{hash_value}.py"
            
            if cfg == "pyproject":
                fpath = outputCfgFiles / f"{hash_value}.toml"
                
            if cfg == "requirements":
                fpath = outputCfgFiles / f"{hash_value}.txt"
 
            if cfg == "pipfileAndLock":
                pipfile_type = Path(repo["path"]).name
                outputCfgFiles = outputCfgFiles.parent / pipfile_type
                if pipfile_type == "Pipfile":
                    fpath = outputCfgFiles / f"{hash_value}"
                    
                if pipfile_type == "Pipfile.lock":
                    fpath = outputCfgFiles / f"{hash_value}.lock" 
                                              
            if fpath.exists():
                continue
            
            # data = json.loads(repo)
            repo_name = repo["repo_name"]
            branch = repo["branch"]
            path = repo["path"]
            download_setupBigQueryData = f"https://raw.githubusercontent.com/{repo_name}/{branch}/{path}"
            success = request_download_url(download_setupBigQueryData, fpath)
            if success: 
                fp.write(f"{hash_value}: {download_setupBigQueryData}\n")


def _worker(cfg_type: str, bigquery_data: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{cfg_type}] Start to collect {bigquery_data.name}")
    get_cfg_from_bigQuery(bigquery_data, output_dir, cfg_type)
    return cfg_type

def downloadConfigFiles(dataInfos, configFiles, max_workers: int = 4):

    cfg_map = {
        "setup": "setup.json",
        "pyproject": "pyproject.json",
        "requirements": "requirements.json",
        "pipfileAndLock": "pipfile_and_lock.json",
    }

    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for cfg_type, json_name in cfg_map.items():
            bigquery_data = dataInfos / json_name
            output_dir = configFiles / cfg_type

            if not bigquery_data.exists():
                print(f"[{cfg_type}] Missing {bigquery_data}, skip")
                continue

            futures.append(ex.submit(_worker, cfg_type, bigquery_data, output_dir))

        for fut in as_completed(futures):
            try:
                cfg_type = fut.result()
                print(f"[{cfg_type}] Done")
            except Exception as e:
                print(f"Task failed: {e}")

