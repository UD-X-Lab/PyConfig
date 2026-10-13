from pathlib import Path
from dataCollector import downloadConfigFiles
from parser.parseToml import parse_toml

baseDir = Path(__file__).parents[0]
dataSource = Path(baseDir / "BigQueryData")
dataInfos = Path(dataSource / "dataInfos")
configFiles = Path(dataSource / "configFiles")

def main():
    downloadConfigFiles(dataInfos, configFiles)



if __name__ == "__main__":
    main()
