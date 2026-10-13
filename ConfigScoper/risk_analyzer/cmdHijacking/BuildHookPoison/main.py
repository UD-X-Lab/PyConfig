import json


COMMON_BACKENDS = {
    "setuptools.build_meta",
    "setuptools.build_meta:__legacy__",
    "poetry.core.masonry.api",
    "poetry.masonry.api",
    "hatchling.build",
    "flit_core.buildapi",
    "pdm.backend",
    "pdm.backend.intree",
    "mesonpy",
    "maturin",
    "scikit_build_core.build",
    "sipbuild.api",
    "wheel_stub.buildapi",
}


def get_experiment_results_1():
  input_file = "data/build-system.build-backend.json"
  input_data = json.load(open(input_file))

  matched_files = dict()
  for filepath, info in input_data["files"].items():
    resolved_value = info["resolved_value"]
    if resolved_value in COMMON_BACKENDS: 
      print(f"Found matched_value: {resolved_value} for {filepath}")

      assert filepath not in matched_files
      matched_files[filepath] = resolved_value

  print("Found {} matched results in total".format(len(matched_files)))

  output_file = "results/result_1.json"
  with open(output_file, 'w+') as f:
    json.dump(matched_files, f, indent=2, sort_keys=True)


def get_experiment_results_2():
  input_file = "data/build-system.requires.json"
  input_data = json.load(open(input_file))


  requires_packages = set()
  for filepath, info in input_data["files"].items():
    resolved_values = info["resolved_value"]
    if not resolved_values:
      continue
    for resolved_value in resolved_values:

      pkgname = resolved_value.split(";", 1)[0]
      pkgname = pkgname.split("=", 1)[0]
      pkgname = pkgname.split(">", 1)[0]
      pkgname = pkgname.split("[", 1)[0]
      pkgname = pkgname.split("<", 1)[0]
      pkgname = pkgname.split("~", 1)[0]
      pkgname = pkgname.split("^", 1)[0]
      pkgname = pkgname.split("!", 1)[0]
      pkgname = pkgname.split("(", 1)[0]
      pkgname = pkgname.strip()

      # print(pkgname, " | ", resolved_value)

      requires_packages.add(pkgname)

  build_backend_file = "data/build-system.build-backend.json"
  build_backend_data = json.load(open(build_backend_file))

  matched_files = dict()
  for filepath, info in build_backend_data["files"].items():
    resolved_value = info["resolved_value"]
    if not resolved_value:
      continue

    resolved_package = resolved_value.split(".", 1)[0]
    if resolved_package in requires_packages: 
      print(f"Found matched_value: {resolved_package} for {filepath}")

      assert filepath not in matched_files
      matched_files[filepath] = resolved_value

  print("Found {} matched results in total".format(len(matched_files)))

  output_file = "results/result_2.json"
  with open(output_file, 'w+') as f:
    json.dump(matched_files, f, indent=2, sort_keys=True)



def main():
  # get_experiment_results_1()
  get_experiment_results_2()

if __name__ == "__main__":
  main()
