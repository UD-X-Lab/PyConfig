from bs4 import BeautifulSoup
from pathlib import Path
import requests
import utils

config_file_json = Path(__file__).parents[0] / "docs"
setupPy_json = config_file_json / "setupPy.json"
test_setupPy_json = config_file_json / "testsetupPy.json"
test_toml_json = config_file_json / "testtoml.json"
requirements_json = config_file_json / "requirements.json"
pipfile_json = config_file_json / "pipfile.json"
pipfile_lock_json = config_file_json / "pipfileLock.json"
pipfile_json = config_file_json / "pipfile.json"

def url_request(url, headers):
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return soup

def extract_keywords(soup):
    result = {}
    for dl in soup.find_all("dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if dt and dd:
            code = dt.find("code")
            if code:
                keyword = code.get_text(strip=True)
                paragraphs = dd.find_all("p")
                if paragraphs:
                    description = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
                else:
                    description = dd.get_text(separator=" ", strip=True)
                
                if "\n" in description:
                    description = description.replace("\n", " ")
                result[keyword] = description
    
    return result

def collect_filed_in_setupPy():
    setuptools_url = "https://setuptools.pypa.io/en/latest/references/keywords.html"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    soup = url_request(setuptools_url, headers)
    result = extract_keywords(soup)
    utils.write_to_json(result, setupPy_json)
    
    
if __name__ == "__main__":
    collect_filed_in_setupPy()