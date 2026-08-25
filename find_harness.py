from pathlib import Path
import ast


for path in Path(".").rglob("*.py"):
    if ".venv" in path.parts:
        continue
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        continue
    if any(isinstance(node, ast.ClassDef) and node.name == "Harness" for node in ast.walk(tree)):
        print(path)
