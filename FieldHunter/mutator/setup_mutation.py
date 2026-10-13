import ast
from collections import defaultdict
from loguru import logger

from global_dir import setupPy_output
import utils

mutation_pep508_url_testcase1 = "pywin32 @ https://github.com/mhammond/pywin32/archive/refs/tags/b306.tar.gz"
mutation_pep508_url_testcase2 = "mdown @ https://github.com/krypton-byte/tiktok-downloader/blob/master/tiktok_downloader/mdown.py"
direct_url_testcase = "https://github.com/mhammond/pywin32/archive/refs/tags/b306.tar.gz#egg=pywin32"
extras_require_pep508_url_testcase = "pywin32 @ https://github.com/mhammond/pywin32/archive/refs/tags/b306.tar.gz"

def parse_keyword_ast(tree, field_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup":
            return node.keywords       

def find_class_names(tree):
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

def check_origin_class(keyword_nodes, class_names, keyword_info):
    for keyword_node in keyword_nodes:
        if isinstance(keyword_node.value, ast.Name):
            keyword_value = keyword_node.value.id
            if keyword_value in class_names:
                keyword_expression = f"{keyword_node.arg}={keyword_value} "
                keyword_info[keyword_node.arg].append(keyword_expression)
                keyword_info[keyword_node.arg].append("Class")
                keyword_info[keyword_node.arg].append("PF")
                
                return keyword_info

def origin_setupPy_class_type(setupPy_field_dir):
    # parse arguments of setup()
    for setup_file in setupPy_field_dir.rglob("*.py"):
        setup_content = utils.read_file(setup_file)
        field_name = setup_file.stem.split("_")[0] 
        
        # if a field is a class, then mark the field as a potential field.
        tree = ast.parse(setup_content)
        keyword_nodes = parse_keyword_ast(tree, field_name)
        keyword_info = defaultdict(list)
        
        # If the type of keyword value is class, we set the keyword as PM(Potential Field)
        class_names = find_class_names(tree)
        keyword_info = check_origin_class(keyword_nodes, class_names, keyword_info)
        logger.success("Detect potential field in <setup.py>")
        for field_name, info in keyword_info.items():
            logger.info(f"Field name: {field_name}")
            logger.info(f"Field exression: {info[0]}")
            logger.info(f"Field value type: {info[1]}")
            logger.info(f"Field type: {info[2]}")

class InstallRequiresModifierPep508(ast.NodeTransformer):
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == 'setup':
            for kw in node.keywords:
                if "requires" in kw.arg:
                    kw.value = ast.List(
                        elts=[
                            ast.Constant(value=mutation_pep508_url_testcase1),
                            ast.Constant(value=mutation_pep508_url_testcase2)
                        ],
                        ctx=ast.Load()
                    )
        return node

class DependencyLinksModifierDirectUrl(ast.NodeTransformer):
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == 'setup':
            for kw in node.keywords:
                if "links" in kw.arg:
                    kw.value = ast.List(
                        elts=[
                            ast.Constant(value=direct_url_testcase)
                        ],
                        ctx=ast.Load()
                    )
        return node
    
class ExtrasRequireModifierDirectUrl(ast.NodeTransformer):
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == 'setup':
            for kw in node.keywords:
                if "require" in kw.arg:
                    kw.value = ast.Dict(
                        keys=[ast.Constant(value='special')],
                        values=[ast.List(
                            elts=[ast.Constant(value=extras_require_pep508_url_testcase)],
                            ctx=ast.Load()
                        )]
                    )
        return node

def mutate_setupPy_pep508_url_type(setupPy_field_dir):
    for setup_file in setupPy_field_dir.rglob("*.py"):
        setup_content = utils.read_file(setup_file)
        field_name = setupPy_field_dir.name
        
        tree = ast.parse(setup_content)
        modifier = InstallRequiresModifierPep508()
        modifier_tree = modifier.visit(tree)
        ast.fix_missing_locations(modifier_tree)
        modified_code = ast.unparse(modifier_tree)
        modified_code_dir = setupPy_field_dir / f"mutation_{field_name}_code.py"
        utils.write_file(modified_code, modified_code_dir)

def origin_setupPy_direct_url(setupPy_field_dir):
    for setup_file in setupPy_field_dir.rglob("*.py"):
        setup_content = utils.read_file(setup_file)
        field_name = setupPy_field_dir.name
        
        tree = ast.parse(setup_content)
        modifier = DependencyLinksModifierDirectUrl()
        modifier_tree = modifier.visit(tree)
        ast.fix_missing_locations(modifier_tree)
        modified_code = ast.unparse(modifier_tree)
        modified_code_dir = setupPy_field_dir / f"mutation_{field_name}_code.py"
        utils.write_file(modified_code, modified_code_dir)

def origin_setupPy_extras_direct_url(setupPy_field_dir):
    for setup_file in setupPy_field_dir.rglob("*.py"):
        setup_content = utils.read_file(setup_file)
        field_name = setupPy_field_dir.name
        
        tree = ast.parse(setup_content)
        modifier = ExtrasRequireModifierDirectUrl()
        modifier_tree = modifier.visit(tree)
        ast.fix_missing_locations(modifier_tree)
        modified_code = ast.unparse(modifier_tree)
        modified_code_dir = setupPy_field_dir / f"mutation_{field_name}_code.py"
        utils.write_file(modified_code, modified_code_dir)

def get_setup_call(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup":
            return node
    return None


def build_mutation_value(mutation_type, original_value):
    if mutation_type == "url":
        return ast.Constant(value="https://example.com/mutated")
    if mutation_type == "function":
        return ast.Name(id="mutated_function", ctx=ast.Load())
    if mutation_type == "class":
        return ast.Name(id="MutatedClass", ctx=ast.Load())
    if mutation_type == "script":
        return ast.List(
            elts=[ast.Constant(value="mutated_script.py")],
            ctx=ast.Load()
        )
    if mutation_type == "command":
        return ast.Constant(value="echo mutated-command")
    return original_value


def build_mutated_helpers(tree):
    existing_names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    insert_index = 0
    while insert_index < len(tree.body) and isinstance(tree.body[insert_index], (ast.Import, ast.ImportFrom)):
        insert_index += 1

    helper_nodes = []
    if "MutatedClass" not in existing_names:
        helper_nodes.append(
            ast.ClassDef(
                name="MutatedClass",
                bases=[ast.Name(id="object", ctx=ast.Load())],
                keywords=[],
                body=[ast.Pass()],
                decorator_list=[]
            )
        )
    if "mutated_function" not in existing_names:
        helper_nodes.append(
            ast.FunctionDef(
                name="mutated_function",
                args=ast.arguments(
                    posonlyargs=[],
                    args=[],
                    kwonlyargs=[],
                    kw_defaults=[],
                    defaults=[]
                ),
                body=[ast.Pass()],
                decorator_list=[]
            )
        )

    for offset, node in enumerate(helper_nodes):
        tree.body.insert(insert_index + offset, node)


def mutate_setupPy_field_dir(setupPy_field_dir):
    for setup_file in setupPy_field_dir.rglob("*.py"):
        if setup_file.name.startswith("mutation_"):
            continue

        setup_content = utils.read_file(setup_file)
        field_name = setupPy_field_dir.name

        for mutation_type in ["url", "function", "class", "script", "command"]:
            tree = ast.parse(setup_content)
            setup_call = get_setup_call(tree)
            if setup_call is None:
                logger.warning(f"No setup() call found in {setup_file}")
                continue

            mutated = False
            for kw in setup_call.keywords:
                if kw.arg == field_name:
                    kw.value = build_mutation_value(mutation_type, kw.value)
                    mutated = True

            if not mutated:
                logger.warning(f"No matching field '{field_name}' in {setup_file}")
                continue

            if mutation_type in {"function", "class"}:
                build_mutated_helpers(tree)

            ast.fix_missing_locations(tree)
            modified_code = ast.unparse(tree)
            mutated_file = setupPy_field_dir / f"mutation_{field_name}_{mutation_type}.py"
            utils.write_file(modified_code, mutated_file)
            logger.success(f"Created mutation: {mutated_file}")


def mutate_setup_file(setupPy_field_dirs):
    if isinstance(setupPy_field_dirs, (list, tuple)):
        for setupPy_field_dir in setupPy_field_dirs:
            mutate_setupPy_field_dir(setupPy_field_dir)
    else:
        mutate_setupPy_field_dir(setupPy_field_dirs)
