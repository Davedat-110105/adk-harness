import ast
from pathlib import Path


root = Path(__file__).resolve().parent
for path in root.rglob("*.py"):
    if any(
        isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.FunctionDef))
        and isinstance(node, ast.ClassDef)
        and node.name == "Harness"
        and any(
            (isinstance(base, ast.Name) and base.id == "Protocol")
            or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
            for base in node.bases
        )
        for node in ast.walk(ast.parse(path.read_text()))
    ):
        Path("answer_path.txt").write_text(f"{path.relative_to(root)}\n")
        break
else:
    raise SystemExit("Harness protocol class not found")
