import json
from pathlib import Path

risk_url_root = Path("/Users/hello/Documents/research/silent_attack_work/ConfigScoper/risk_analyzer/risk_urls")
danglingSouce = risk_url_root / "dangling"
subdomainSource = risk_url_root / "expiredDomain"
mimSource = risk_url_root / "MIM"
cfgBigURL = Path("/Users/hello/Documents/research/silent_attack_work/ConfigScoper/stats-output") 


    
def readJson(path):
    json_path = Path(path)
    with json_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def writeJson(path, data):
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def reqMalURL(directURL, reqMalURLdir, outReqMalURLdir):
    reqContent = readJson(reqMalURLdir)
    reqURLInfo = reqContent["direct_file_by_url_sources"]
    
    directURL = readJson(directURL)
    
    reqBQURL = dict()
    total = 0
    for malURL, files in reqURLInfo.items():
        for url, num in directURL.items():
            if malURL == url:
                reqBQURL[malURL] = num
                total += num
    reBQMalURL = {
        "total": 
            total,
        "malURL": 
            reqBQURL
    }
    writeJson(outReqMalURLdir, reBQMalURL) 

def reqDangling(directURL, vcsURL):
    reqMalURLdir = danglingSouce / "missing_package_requirements_link_sources.json"
    
    outReqMalURLdir = danglingSouce / "reqBQMalDirectURL.json"    
    reqMalURL(directURL, reqMalURLdir, outReqMalURLdir)
    
    outReqMalURLdir = danglingSouce / "reqBQMalVcsURL.json" 
    reqMalURL(vcsURL, reqMalURLdir, outReqMalURLdir)

def setupDangling(inputOrg, inputMal, outputMal):
    inputMal = readJson(inputMal)
    inputOrg = readJson(inputOrg)
    depenTotal = 0
    depenBQURL = dict()
    for fieldInfo in inputMal:
        for url,num in inputOrg.items():
            if fieldInfo.get("url") in url:
                depenBQURL[fieldInfo.get("url")] = num
                depenTotal += num
    depenBQMalURL = {
        "total": depenTotal,
        "malURL": depenBQURL
    }
    writeJson(outputMal, depenBQMalURL)

def test_set(danglingSouce):
    inputsetMalSource = danglingSouce / "missing_package_urls_in_setup_fields.json"
    setBigURL = cfgBigURL / "parseSetup"

    inputDepenOrg = setBigURL / "dependency_links.json"
    outputDenMal = danglingSouce / "setBQMalDepenURL.json"
    setupDangling(inputDepenOrg, inputsetMalSource, outputDenMal)
    
    inputExtOrg = setBigURL / "extrasRequire.json"
    outputExtMal = danglingSouce / "setBQMalExtURL.json"    
    setupDangling(inputExtOrg, inputsetMalSource, outputExtMal)

    inputInsOrg = setBigURL / "install_requires.json"
    outputInsMal = danglingSouce / "setBQMalInsURL.json"    
    setupDangling(inputInsOrg, inputsetMalSource, outputInsMal)
    
    inputTesOrg = setBigURL / "tests_require.json"
    outputTesMal = danglingSouce / "setBQMalTesURL.json"    
    setupDangling(inputTesOrg, inputsetMalSource, outputTesMal)

def test_toml(danglingSouce):
    inputTomlMalSource = danglingSouce / "missing_package_urls_in_toml_fields.json"
    tomlBigURL = cfgBigURL / "parseToml"

    inputBuildOrg = tomlBigURL / "build-system.requires.json"
    outputBuildMal = danglingSouce / "tomlBQMalBuildURL.json"
    setupDangling(inputBuildOrg, inputTomlMalSource, outputBuildMal)    

    inputDepenOrg = tomlBigURL / "dependency-groups.json"
    outputDepenMal = danglingSouce / "tomlBQMalDepenURL.json"
    setupDangling(inputDepenOrg, inputTomlMalSource, outputDepenMal)    

    inputProDepenOrg = tomlBigURL / "project.dependencies.json"
    outputProDepenMal = danglingSouce / "tomlBQMalProDepenURL.json"
    setupDangling(inputProDepenOrg, inputTomlMalSource, outputProDepenMal)    

    inputProOpOrg = tomlBigURL / "project.optional-dependencies.json"
    outputProOpMal = danglingSouce / "tomlBQMalProOpURL.json"
    setupDangling(inputProOpOrg, inputTomlMalSource, outputProOpMal)    

    inputPoedepenOrg = tomlBigURL / "tool.poetry.dependencies.json"
    outputPoedepenMal = danglingSouce / "tomlBQMalPoedepenURL.json"
    setupDangling(inputPoedepenOrg, inputTomlMalSource, outputPoedepenMal)    

    inputPoeDevOrg = tomlBigURL / "tool.poetry.dev-dependencies.json"
    outputPoeDevMal = danglingSouce / "tomlBQMalPoeDevURL.json"
    setupDangling(inputPoeDevOrg, inputTomlMalSource, outputPoeDevMal)    

def dangling():
    # req
    reqSource = Path("/Users/hello/Documents/research/silent_attack_work/ConfigScoper/parser/parseReq/output/fieldInfo/R1")
    directURL = reqSource / "directURL.json"
    vcsURL = reqSource / "vcsURL.json"
    reqDangling(directURL, vcsURL)   
    
    # Pipfile and Pipfile.lock is 0
    
    # setup
    test_set(danglingSouce)
    
    # toml
    test_toml(danglingSouce)

def expireCfg(singlecfgBigUrl, expDomain, output_dir):
    
    for fieldFile in singlecfgBigUrl.rglob("*.json"):
        oriContent = readJson(fieldFile)
        
        totalNum = 0
        tomlBQURL = dict()
        for malD in expDomain:
            for url, num in oriContent.items():
                if malD in url:
                    totalNum += num 
                    tomlBQURL[url] = num

        if totalNum:
            tomlBQMalURL = {"total": totalNum, "malURL": tomlBQURL}
            outpath = output_dir / fieldFile.name
            writeJson(outpath, tomlBQMalURL)    

def expiredDomain():
    inputDomainSource = subdomainSource / "expired_domains_dedup.json"
    expDomain = readJson(inputDomainSource)
    expDomain = expDomain["domains"]
    bigCfgDir = ["parsePipfile", "parsePipfileLock", "parseSetup", "parseToml"]
    for cfg in bigCfgDir:
        singlecfgBigUrl = cfgBigURL / cfg
        expireCfg(singlecfgBigUrl, expDomain, subdomainSource)

def MIMCfg(singlecfgBigUrl, expDomain, output_dir):
    
    for fieldFile in singlecfgBigUrl.rglob("*.json"):
        oriContent = readJson(fieldFile)
        
        totalNum = 0
        tomlBQURL = dict()
        for malD in expDomain:
            for url, num in oriContent.items():
                if url.startswith(malD):
                    totalNum += num 
                    tomlBQURL[url] = num

        if totalNum:
            tomlBQMalURL = {"total": totalNum, "malURL": tomlBQURL}
            outpath = output_dir / fieldFile.name
            writeJson(outpath, tomlBQMalURL)    



def get_mim_data():
    mim_blacklist = mimSource / "no_jump_to_https.txt"
    with open(mim_blacklist) as f:
        expDomain = []
        for line in f.readlines():
            line = line.split("@", 1)[0]
            line = line.split("#", 1)[0]
            expDomain.append(line.strip())
    print(f"Found {len(expDomain)} records in blacklist")
    
    bigCfgDir = ["parsePipfile", "parsePipfileLock", "parseSetup", "parseToml"]
    for cfg in bigCfgDir:
        singlecfgBigUrl = cfgBigURL / cfg
        MIMCfg(singlecfgBigUrl, expDomain, mimSource)    


def get_subdomain_hijack_data():
    inputDomainSource = risk_url_root / "subdomainHijack/takeover_domains"
    with open(inputDomainSource) as f:
        expDomain = [line.strip() for line in f.readlines()]

    
    bigCfgDir = ["parsePipfile", "parsePipfileLock", "parseSetup", "parseToml"]
    for cfg in bigCfgDir:
        singlecfgBigUrl = cfgBigURL / cfg
        expireCfg(singlecfgBigUrl, expDomain,  risk_url_root / "subdomainHijack")

def get_virustotal_data():
    inputDomainSource = risk_url_root / "virustotal/virustotal_alive_non_official_report.json"
    with open(inputDomainSource) as f:
        input_data = json.load(f)
        expDomain = [info["url"].strip() for info in input_data]
    print(f"Found {len(expDomain)} records in blacklist")
    
    bigCfgDir = ["parsePipfile", "parsePipfileLock", "parseSetup", "parseToml"]
    for cfg in bigCfgDir:
        singlecfgBigUrl = cfgBigURL / cfg
        expireCfg(singlecfgBigUrl, expDomain,  risk_url_root / "virustotal")


def main():
    # dangling()
    # expiredDomain()
    # get_mim_data()
    get_subdomain_hijack_data()
    # get_virustotal_data()
    
if __name__ == "__main__":
    main()
