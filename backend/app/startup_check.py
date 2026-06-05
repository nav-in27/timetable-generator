import os
import ast
import sys

def check_orm_loaders(directory: str) -> list:
    """
    Scans all Python files in the given directory to ensure that
    SQLAlchemy ORM loaders (joinedload, selectinload, subqueryload, contains_eager)
    are imported if they are used.
    """
    errors = []
    target_loaders = {'joinedload', 'selectinload', 'subqueryload', 'contains_eager'}

    for root, _, files in os.walk(directory):
        for file in files:
            if not file.endswith('.py'):
                continue

            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                try:
                    content = f.read()
                    tree = ast.parse(content, filename=filepath)
                except SyntaxError as e:
                    errors.append(f"SyntaxError in {filepath}: {e}")
                    continue
                except Exception as e:
                    errors.append(f"Could not read {filepath}: {e}")
                    continue

            # Find all imported names
            imported_names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_names.add(alias.name)
                        if alias.asname:
                            imported_names.add(alias.asname)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        imported_names.add(alias.name)
                        if alias.asname:
                            imported_names.add(alias.asname)

            # Check if any target loader is used
            used_loaders = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    if node.id in target_loaders:
                        used_loaders.add(node.id)

            # Compare used vs imported
            missing = used_loaders - imported_names
            if missing:
                # Some files might import them locally inside a function.
                # To be absolutely strict and fail fast, we demand them at the module level
                # or we just do a simple AST check for any Import/ImportFrom anywhere in the file.
                # Since we walked the entire tree, `imported_names` contains all imports (even local).
                errors.append(
                    f"[STARTUP VALIDATION FAILED] File '{filepath}' uses ORM loaders {missing} "
                    f"but they are not imported."
                )

    return errors

def run_startup_validation():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    print("Running project-wide static checks before startup...")
    errors = check_orm_loaders(backend_dir)
    
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print("\nCRITICAL: Startup blocked due to missing imports. Fix the errors above.", file=sys.stderr)
        sys.exit(1)
    
    print("Static checks passed. No missing ORM loader imports found.")

if __name__ == '__main__':
    run_startup_validation()
