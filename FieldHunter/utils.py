import json
import tomli
import tomli_w

def write_to_json(content, json_file):
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
        
def read_from_json(file):
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)
        
def read_file(file):
    with open(file) as file:
        return file.read()

def write_file(content, file):
    with open(file, "w") as f:
        f.write(content)
        
def read_toml(file):
    with open(file, "rb") as f:
        return tomli.load(f)
    
def write_toml(content, file):
    with open(file, "wb") as f:
        f.write(tomli_w.dumps(content).encode("utf-8"))