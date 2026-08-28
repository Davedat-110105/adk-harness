"""Check release archives: ``python tests/check_distribution.py dist/*``."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def check(path: Path) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        assert "adk_harness/plugins/antigravity/plugin.json" in names, "wheel is missing its plugin"
        for module in ("coding/harness_agent", "governance/content_armor", "governance/stores",
                       "workspace/app", "mcp/server", "cli/main"):
            assert f"adk_harness/{module}.py" in names, f"missing canonical module {module}"
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
        assert any(name.endswith("/plugins/antigravity/plugin.json") for name in names)
    assert any(PurePosixPath(name).name == "LICENSE" for name in names), "missing license"
    for name in names:
        parts = PurePosixPath(name).parts
        assert not any(part.startswith(".env") or part == ".adk" for part in parts), name
        assert not any(part.endswith(".db") or ".db-" in part for part in parts), name
    print(f"{path.name}: plugin, license, canonical modules and runtime exclusions verified")


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        check(Path(argument))
