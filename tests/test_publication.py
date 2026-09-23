import re
from pathlib import Path


def test_ci_workflow_contains_all_publication_gates():
    text = Path(".github/workflows/ci.yml").read_text()
    for marker in (
        "quality:",
        "tests:",
        "demo:",
        "publication:",
        'python-version: ["3.10", "3.12", "3.14"]',
        "ruff check",
        "python -m build",
        "scripts/verify_demo.py",
        "scripts/check_publication.py",
    ):
        assert marker in text

    tests_job = re.search(r"(?ms)^  tests:\n.*?(?=^  \S|\Z)", text).group()
    assert 'python -m pip install -e ".[dev,viz]"' in tests_job
    assert "python -m pytest -q" in tests_job


def test_readme_contains_public_story_and_runnable_demo():
    text = Path("README.md").read_text(encoding="utf-8")
    required = [
        "# Auditable Portfolio Lab",
        "![Synthetic benchmark overview](assets/benchmark-overview.png)",
        "## What It Demonstrates",
        "## Five-Minute Demo",
        "--allow-synthetic-demo",
        "## How AI Was Used",
        "docs/ai-assisted-development.md",
        "## Architecture",
        "docs/architecture.md",
        "## Evaluation and Reproducibility",
        "## Data Boundary and Limitations",
        "not investment advice",
    ]
    for marker in required:
        assert marker in text, f"README.md missing {marker}"


def test_required_public_documents_have_expected_evidence_sections():
    required = {
        "docs/architecture.md": ["## Data Flow", "## Component Boundaries"],
        "docs/ai-assisted-development.md": [
            "## Source Qualification",
            "## Drawdown Correction",
            "## Reproducible Artifacts",
            "AI contribution",
            "Validation gate",
        ],
        "docs/evaluation.md": ["## Test Layers", "## Release Gates"],
        "docs/data-and-limitations.md": [
            "## Public Demo",
            "## Redistribution Boundary",
            "## Known Limitations",
        ],
    }
    for filename, markers in required.items():
        text = Path(filename).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in text, f"{filename} missing {marker}"


def test_publication_audit_accepts_clean_tree(tmp_path):
    from scripts.check_publication import audit_tree

    (tmp_path / "README.md").write_text("# Demo\n[Architecture](docs/architecture.md)\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "architecture.md").write_text("# Architecture\n")
    assert (
        audit_tree(
            tmp_path,
            [Path("README.md"), Path("docs/architecture.md")],
        )
        == []
    )


def test_publication_audit_reports_private_paths_content_and_broken_links(tmp_path):
    from scripts.check_publication import audit_tree

    private_home = "/" + "Users/private/project"
    local_uri = "file:" + "///" + "Users/private/data.csv"
    (tmp_path / "README.md").write_text(f"{private_home}\n{local_uri}\n[Missing](docs/missing.md)\n")
    violations = audit_tree(
        tmp_path,
        [Path("README.md"), Path(".superpowers/review.md")],
    )
    assert any("forbidden tracked path" in item for item in violations)
    assert any("absolute user path" in item for item in violations)
    assert any("file URI" in item for item in violations)
    assert any("broken relative link" in item for item in violations)


def test_publication_audit_reports_windows_home_path(tmp_path):
    from scripts.check_publication import audit_tree

    windows_home = "C:" + "\\" + r"Users\alice\file.txt\n"
    (tmp_path / "README.md").write_text(windows_home)
    assert audit_tree(tmp_path, [Path("README.md")]) == ["absolute user path: README.md"]
