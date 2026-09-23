from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Sequence

FORBIDDEN_PATH_PARTS = {
    ".superpowers",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    ".DS_Store",
}
FORBIDDEN_FILENAMES = {
    "investor_planning_context.json",
    "2026-09-20-investor-context-and-benchmarks.md",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def tracked_paths(root: Path) -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return [Path(item.decode()) for item in output.split(b"\0") if item]


def audit_tree(root: Path, paths: Sequence[Path]) -> list[str]:
    violations: list[str] = []
    home_pattern = "/" + "Users/"
    file_uri_pattern = "file:" + "///"
    for relative in paths:
        if FORBIDDEN_PATH_PARTS.intersection(relative.parts) or relative.name in FORBIDDEN_FILENAMES:
            violations.append(f"forbidden tracked path: {relative.as_posix()}")
            continue
        path = root / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if home_pattern in text or re.search(r"[A-Za-z]:\\Users\\", text):
            violations.append(f"absolute user path: {relative.as_posix()}")
        if file_uri_pattern in text:
            violations.append(f"file URI: {relative.as_posix()}")
        if relative.suffix.lower() == ".md":
            for target in MARKDOWN_LINK.findall(text):
                clean = target.split("#", 1)[0]
                if not clean or clean.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                if not (path.parent / clean).resolve().exists():
                    violations.append(f"broken relative link in {relative.as_posix()}: {target}")
    return sorted(set(violations))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = audit_tree(root, tracked_paths(root))
    if violations:
        print("\n".join(violations))
        return 1
    print("publication audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
