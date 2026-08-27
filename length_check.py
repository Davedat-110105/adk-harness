from pathlib import Path


answer_path = Path("answer_path.txt").read_text().strip()
content = "A" * 1000 if answer_path == "src/adk_harness/harness/protocol.py" else "B" * 5000
Path("length_check.txt").write_text(content)
