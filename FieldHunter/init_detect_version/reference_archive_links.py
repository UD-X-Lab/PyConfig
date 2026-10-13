from pathlib import Path
import re
from urllib.parse import urlparse
from collections import defaultdict
import Levenshtein

import utils

def detect_direct_external_links(target_repo_dir):
    reference_malicious_archive_links(target_repo_dir)

def scan_requirements_and_collect_urls(target_repo_dir):
    requirements_dir = Path(target_repo_dir).rglob("requirements.txt")
    if requirements_dir:
        requirement_file = scan_requirements(requirements_dir)
        urls = collect_urls(requirement_file)
        
        return urls

def scan_requirements(requirements_dir):
    print("******Find the requirements.txt: ")
    for requirement_file in requirements_dir:
        print(requirement_file)
        return requirement_file
        
def collect_urls(requirement_file):
    url_pattern = re.compile(r'https?://[^\s\'"]+')
    urls = []
    with requirement_file.open("r", encoding="utf-8") as f:
        for line in f:
            matches = url_pattern.findall(line)
            urls.extend(matches)
    
    print("******Extract lins from requirements.txt")
    for url in urls:
        print(url)
    
    return urls

def check_urls(urls):
    check_domain_if_malicious(urls)
    check_download_packages_if_malicious()

def check_domain_if_malicious(urls):
    domain_groups = group_urls_by_domain(urls)
    print_grouped_urls(domain_groups)
    
    match_black_list(domain_groups)

    typosquat_domain(domain_groups)

def print_grouped_urls(domain_groups):
    print("******Group urls by domain name:")
    for domain, urls in domain_groups.items():
        print(f"domain: {domain}")
        for url in urls:
            print(f" - {url}")

def group_urls_by_domain(urls):
    groups = defaultdict(list)
    for url in urls:
        domain = urlparse(url).netloc
        groups[domain].append(url)
    
    return groups

def match_black_list(domain_groups): 
    # Match urls to balck list domain. If the domain of the url in black list domain, the url is a malicious one.
    malicious_domains = black_list_domain()
    malicious_urls = []
    for domain, urls in domain_groups.items():
        if domain in malicious_domains:
            malicious_urls.extend(urls)
    
    return malicious_urls

def typosquat_domain(domain_groups, threshold=4):
    similar_to_white_list_domain(domain_groups, threshold)
    similar_to_self_domain(domain_groups, threshold)

def similar_to_white_list_domain(domain_groups, threshold):
    official_domains = white_list_domain()
    suspicious_pairs = []
    for domain, urls in domain_groups.items():
        for official_domain in official_domains:
            distance = Levenshtein.distance(domain, official_domain)
            if 0 < distance <= threshold:
                suspicious_domain_and_url = {domain: urls}
                suspicious_pairs.append((official_domain, suspicious_domain_and_url, distance))
                
    print_typosquatting_domain_and_urls_via_white(suspicious_pairs)
    
def print_typosquatting_domain_and_urls_via_white(suspicious_pairs):
    print("******typosquatting domain and distance via white list:")
    print(" - domains in white list <-> domains in requirements: [urls]:")
    for official_domain, suspicious_domain_and_url, distance in suspicious_pairs:
        for suspicious_domain, suspicious_url in suspicious_domain_and_url.items():
            print(f" - {official_domain} <-> {suspicious_domain}: {suspicious_url} <distance: {distance}>")

def similar_to_self_domain(domain_groups, threshold):
    suspicious_pairs = []
    for domain1, urls1 in domain_groups.items():
        for domain2, urls2 in domain_groups.items():
            distance = Levenshtein.distance(domain1, domain2)
            if 0 < distance <= threshold:
                suspicious1_domain_and_urls = {domain1: urls1}
                suspicious2_domain_and_urls = {domain2: urls2}
                suspicious_pairs.append((suspicious1_domain_and_urls, suspicious2_domain_and_urls, distance))
    print_typosquatting_domain_and_urls_via_self(suspicious_pairs)
    
def print_typosquatting_domain_and_urls_via_self(suspicious_pairs):
    print("******typosquatting domain and distance via self:")
    print(" - domains in self [urls] <-> domains in self: [urls]:")
    for suspicious1_domain_and_urls, suspicious2_domain_and_urls, distance in suspicious_pairs:
        for domain1, urls1 in suspicious1_domain_and_urls.items():
            for domain2, urls2 in suspicious2_domain_and_urls.items():
                print(f" - {domain1}: {urls1} <-> {domain2}: {urls2} <distance: {distance}>")

def white_list_domain():
    official_domain_dir = Path(__file__).parents[0] / "official_domain.txt"
    official_domains = []
    official_domains = utils.read_file(official_domain_dir, official_domains)
    
    return official_domains

def black_list_domain():
    malicious_domain_dir = Path(__file__).parents[0] / "malicious_domain.txt"
    malicious_domains = []
    malicious_domains = utils.read_file(malicious_domain_dir, malicious_domains)
    
    return malicious_domains

def check_download_packages_if_malicious():
    pass


def reference_malicious_archive_links(target_repo_dir):
    # 1. scan the requirements.txt and get the url collections
    urls = scan_requirements_and_collect_urls(target_repo_dir)
    
    # 2. check if the direct file links are official website, if they are, check these packages and see if they are benign or not.
    check_urls(urls)
    
    # 3. if they are not official:
    #   (1). if they are dangling, they could be took over by attackers
    #   (2). send these urls to virus-total
    #   (3). manually inspect the packages code
    
if __name__ == "__main__":
    target_repo_dir = Path(__file__).parents[1] / "malicious_repo_test_demo"
    detect_direct_external_links(target_repo_dir)