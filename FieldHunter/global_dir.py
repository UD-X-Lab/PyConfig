from pathlib import Path

output_parent_dir = Path(__file__).parents[0] / "output"
setupPy_output = output_parent_dir / "setupPy"
toml_output = output_parent_dir / "pyprojectToml"
requirements_output = output_parent_dir / "requirements"
pipfile_output = output_parent_dir / "pipfile"
pipfile_lock_output = output_parent_dir / "pipfile_lock"