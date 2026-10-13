from pathlib import Path

from collect_fields import setupPy_json, test_setupPy_json, test_toml_json, requirements_json, pipfile_json, pipfile_lock_json
from model import chat_llm
from mutator.setup_mutation import mutate_setup_file
from mutator.toml_mutation import mutate_toml_file
from mutator.req_mutation import process_requirements_root
from mutator.pipfile_mutation import scan_pipfile_root
from mutator.pipfile_lock_mutation import scan_pipfile_lock_root
from global_dir import setupPy_output, toml_output, requirements_output, pipfile_output, pipfile_lock_output
import utils

def extract_code_and_cmd_from_output(output_content, field, field_dir):
    # extract code output
    start_code = output_content.find("<code>") + len("<code>")
    end_code = output_content.find("</code>")
    code_content = output_content[start_code:end_code].strip()
    code_dir = field_dir / f"{field}_code.py"
    utils.write_file(code_content, code_dir)
    
    # extract command output
    start_cmd = output_content.find("<cmd>") + len("<cmd>")
    end_cmd = output_content.find("</cmd>")
    cmd_content = output_content[start_cmd:end_cmd].strip()
    cmd_dir = field_dir / f"{field}_cmd.sh"
    utils.write_file(cmd_content, cmd_dir)

def extract_toml_and_cmd_from_output(output_content, field, field_dir):
    # extract code output
    start_code = output_content.find("<code>") + len("<code>")
    end_code = output_content.find("</code>")
    code_content = output_content[start_code:end_code].strip()
    code_dir = field_dir / f"{field}_pyproject.toml"
    utils.write_file(code_content, code_dir)
    
    # extract command output
    start_cmd = output_content.find("<cmd>") + len("<cmd>")
    end_cmd = output_content.find("</cmd>")
    cmd_content = output_content[start_cmd:end_cmd].strip()
    cmd_dir = field_dir / f"{field}_cmd.sh"
    utils.write_file(cmd_content, cmd_dir)

def format_setup_priming(setup_config_file_dir):
    setup_template_content = utils.read_file(setup_config_file_dir)
    setup_field = utils.read_from_json(setupPy_json)
    # setup_field = utils.read_from_json(test_setupPy_json)
    field_dirs = []
    for keyword, description in setup_field.items():
        setup_prompt = setup_template_content.replace("{FIELD}", keyword)
        setup_prompt = setup_prompt.replace("{DESCRIPTION}", description)
        field_dir = setupPy_output / keyword
        field_dir.mkdir(exist_ok=True)
        field_output = field_dir / f"{keyword}_output.txt"
        chat_llm(setup_prompt, field_output)

        # extract code to python file and command to shell from output
        output_content = utils.read_file(field_output)
        extract_code_and_cmd_from_output(output_content, keyword, field_dir)
        
        field_dirs.append(field_dir)
    return field_dirs

def generate_field_usage_for_setupPy():
    prompts_dir = Path(__file__).parents[0] / "prompts"
    priming_prompts = prompts_dir / "priming_prompt"
    
    # generate usage example for `setup.py`
    setup_config_file_dir = priming_prompts / "setupPy_init_template.txt"
    field_dirs = format_setup_priming(setup_config_file_dir)
    return field_dirs

def format_toml_priming(toml_config_file_dir):
    toml_template_content = utils.read_file(toml_config_file_dir)
    # setup_field = utils.read_from_json(setupPy_json)
    toml_field = utils.read_from_json(test_toml_json)
    field_dirs = []
    for keyword, description in toml_field.items():
        toml_prompt = toml_template_content.replace("{FIELD}", keyword)
        toml_prompt = toml_prompt.replace("{DESCRIPTION}", description)
        # main_table = keyword.split(".")[0].strip("[]")
        # sub_table = keyword.split(".")[1]
        # field_folder_name = main_table + "_" + sub_table
        field_dir = toml_output / keyword
        field_dir.mkdir(exist_ok=True)
        field_output = field_dir / f"{keyword}_output.txt"
        chat_llm(toml_prompt, field_output)

        # extract code to python file and command to shell from output
        # TODO:Need to add retry three times
        output_content = utils.read_file(field_output)
        extract_toml_and_cmd_from_output(output_content, keyword, field_dir)
        
        field_dirs.append(field_dir)
    return field_dirs

def extract_requirements_and_cmd_from_output(output_content, field, field_dir):
    # extract requirements output
    start_code = output_content.find("<code>") + len("<code>")
    end_code = output_content.find("</code>")
    code_content = output_content[start_code:end_code].strip()
    code_dir = field_dir / "requirements.txt"
    utils.write_file(code_content, code_dir)
    
    # extract command output
    start_cmd = output_content.find("<cmd>") + len("<cmd>")
    end_cmd = output_content.find("</cmd>")
    cmd_content = output_content[start_cmd:end_cmd].strip()
    cmd_dir = field_dir / f"{field}_cmd.sh"
    utils.write_file(cmd_content, cmd_dir)


def extract_pipfile_and_cmd_from_output(output_content, field, field_dir):
    # extract Pipfile output
    start_code = output_content.find("<code>") + len("<code>")
    end_code = output_content.find("</code>")
    code_content = output_content[start_code:end_code].strip()
    code_dir = field_dir / "Pipfile"
    utils.write_file(code_content, code_dir)
    
    # extract command output
    start_cmd = output_content.find("<cmd>") + len("<cmd>")
    end_cmd = output_content.find("</cmd>")
    cmd_content = output_content[start_cmd:end_cmd].strip()
    cmd_dir = field_dir / f"{field}_cmd.sh"
    utils.write_file(cmd_content, cmd_dir)


def extract_pipfile_lock_and_cmd_from_output(output_content, field, field_dir):
    # extract Pipfile.lock output
    start_code = output_content.find("<code>") + len("<code>")
    end_code = output_content.find("</code>")
    code_content = output_content[start_code:end_code].strip()
    code_dir = field_dir / "Pipfile.lock"
    utils.write_file(code_content, code_dir)
    
    # extract command output
    start_cmd = output_content.find("<cmd>") + len("<cmd>")
    end_cmd = output_content.find("</cmd>")
    cmd_content = output_content[start_cmd:end_cmd].strip()
    cmd_dir = field_dir / f"{field}_cmd.sh"
    utils.write_file(cmd_content, cmd_dir)


def format_requirements_priming(requirements_config_file_dir):
    requirements_template_content = utils.read_file(requirements_config_file_dir)
    requirements_field = utils.read_from_json(requirements_json)
    field_dirs = []
    for keyword, description in requirements_field.items():
        requirements_prompt = requirements_template_content.replace("{FIELD}", keyword)
        requirements_prompt = requirements_prompt.replace("{DESCRIPTION}", description)
        field_dir = requirements_output / keyword
        field_dir.mkdir(exist_ok=True)
        field_output = field_dir / f"{keyword}_output.txt"
        chat_llm(requirements_prompt, field_output)

        # extract requirements text and command to shell from output
        # TODO:Need to add retry three times
        output_content = utils.read_file(field_output)
        extract_requirements_and_cmd_from_output(output_content, keyword, field_dir)
        
        field_dirs.append(field_dir)
    return field_dirs


def format_pipfile_priming(pipfile_config_file_dir):
    pipfile_template_content = utils.read_file(pipfile_config_file_dir)
    pipfile_field = utils.read_from_json(pipfile_json)
    field_dirs = []
    for keyword, description in pipfile_field.items():
        pipfile_prompt = pipfile_template_content.replace("{FIELD}", keyword)
        pipfile_prompt = pipfile_prompt.replace("{DESCRIPTION}", description)
        field_dir = pipfile_output / keyword
        field_dir.mkdir(exist_ok=True)
        field_output = field_dir / f"{keyword}_output.txt"
        chat_llm(pipfile_prompt, field_output)

        # extract Pipfile text and command to shell from output
        # TODO:Need to add retry three times
        output_content = utils.read_file(field_output)
        extract_pipfile_and_cmd_from_output(output_content, keyword, field_dir)
        
        field_dirs.append(field_dir)
    return field_dirs


def generate_field_usage_for_toml():
    prompts_dir = Path(__file__).parents[0] / "prompts"
    priming_prompts = prompts_dir / "priming_prompt"
    
    toml_config_file_dir = priming_prompts / "pyprojectToml_priming_template.txt"
    field_dirs = format_toml_priming(toml_config_file_dir)
    return field_dirs


def generate_field_usage_for_requirements():
    prompts_dir = Path(__file__).parents[0] / "prompts"
    priming_prompts = prompts_dir / "priming_prompt"
    
    requirements_config_file_dir = priming_prompts / "requirements_priming_template.txt"
    field_dirs = format_requirements_priming(requirements_config_file_dir)
    return field_dirs


def generate_field_usage_for_pipfile():
    prompts_dir = Path(__file__).parents[0] / "prompts"
    priming_prompts = prompts_dir / "priming_prompt"
    
    pipfile_config_file_dir = priming_prompts / "lockfile_priming_template.txt"
    field_dirs = format_pipfile_priming(pipfile_config_file_dir)
    return field_dirs


def format_pipfile_lock_priming(pipfile_lock_config_file_dir):
    lock_template_content = utils.read_file(pipfile_lock_config_file_dir)
    lock_field = utils.read_from_json(pipfile_lock_json)
    field_dirs = []
    for keyword, description in lock_field.items():
        lock_prompt = lock_template_content.replace("{FIELD}", keyword)
        lock_prompt = lock_prompt.replace("{DESCRIPTION}", description)
        field_dir = pipfile_lock_output / keyword
        field_dir.mkdir(exist_ok=True)
        field_output = field_dir / f"{keyword}_output.txt"
        chat_llm(lock_prompt, field_output)

        # extract Pipfile.lock text and command to shell from output
        # TODO:Need to add retry three times
        output_content = utils.read_file(field_output)
        extract_pipfile_lock_and_cmd_from_output(output_content, keyword, field_dir)
        
        field_dirs.append(field_dir)
    return field_dirs


def generate_field_usage_for_pipfile_lock():
    prompts_dir = Path(__file__).parents[0] / "prompts"
    priming_prompts = prompts_dir / "priming_prompt"
    
    pipfile_lock_config_file_dir = priming_prompts / "lockfile_priming_template.txt"
    field_dirs = format_pipfile_lock_priming(pipfile_lock_config_file_dir)
    return field_dirs


if __name__ == "__main__":
    output_parent_dir = Path(__file__).parents[0] / "output"

    # generate and mutate pyproject.toml field usage
    generate_field_usage_for_toml()
    toml_field_dir = output_parent_dir / "pyprojectToml"
    mutate_toml_file(toml_field_dir)
    
    # generate and mutate setup.py field usage
    generate_field_usage_for_setupPy()
    setupPy_field_dir = output_parent_dir / "setupPy"
    mutate_setup_file(setupPy_field_dir)

    # generate and mutate requirements.txt field usage
    generate_field_usage_for_requirements()
    requirements_field_dir = output_parent_dir / "requirements"
    process_requirements_root(requirements_field_dir)

    # generate and mutate Pipfile field usage
    generate_field_usage_for_pipfile()
    pipfile_field_dir = output_parent_dir / "pipfile"
    scan_pipfile_root(pipfile_field_dir)

    # generate and mutate Pipfile.lock field usage
    generate_field_usage_for_pipfile_lock()
    pipfile_lock_field_dir = output_parent_dir / "pipfile_lock"
    scan_pipfile_lock_root(pipfile_lock_field_dir)
    
