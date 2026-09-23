import re
from pathlib import Path

import pytest


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


def test_readme_retains_runnable_quickstart_and_product_boundaries():
    text = Path("README.md").read_text(encoding="utf-8")
    for marker in (
        "## Quick start",
        "pcopt benchmark",
        "--allow-synthetic-demo",
        "repository-authored synthetic data",
        "## Project status and limitations",
        "docs/data-and-limitations.md",
    ):
        assert marker in text, f"README.md missing product contract: {marker}"


def test_readme_retains_core_engineering_and_qualification_links():
    text = Path("README.md").read_text(encoding="utf-8")
    for target in (
        "docs/architecture.md",
        "docs/evaluation.md",
        "docs/decisions/001-fail-closed-data-qualification.md",
    ):
        assert f"]({target})" in text, f"README.md missing documentation link: {target}"

    required_sections = {
        Path("docs/architecture.md"): ("## Product Boundary", "## Component Boundaries"),
        Path("docs/evaluation.md"): ("## Test Layers", "## Release Gates"),
        Path("docs/data-and-limitations.md"): ("## Bundled Sample", "## Known Limitations"),
        Path("docs/decisions/001-fail-closed-data-qualification.md"): ("## Decision", "## Consequences"),
    }
    for path, headings in required_sections.items():
        document = path.read_text(encoding="utf-8")
        for heading in headings:
            assert heading in document, f"{path} missing product contract: {heading}"


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


@pytest.mark.parametrize(
    ("relative", "text", "matched"),
    [
        (Path("README.md"), "Built with AI assistance.", "AI"),
        (Path("docs/product.md"), "A polished showcase.", "showcase"),
        (Path("README.md"), "Designed for recruiters.", "recruiters"),
        (Path("docs/product.md"), "An interview project.", "interview"),
        (Path("README.md"), "A portfolio piece.", "portfolio piece"),
        (Path("docs/product.md"), "Multiple portfolio pieces.", "portfolio pieces"),
        (Path("README.md"), "Built for a hiring manager.", "hiring manager"),
        (Path("docs/product.md"), "Written for hiring reviewers.", "hiring reviewers"),
        (Path("README.md"), "Resume-oriented project copy.", "Resume-oriented"),
        (Path("docs/product.md"), "Resumé-ready summary.", "Resumé-ready"),
        (Path("README.md"), "A résumé project.", "résumé project"),
        (Path("docs/product.md"), "CV-oriented wording.", "CV-oriented"),
    ],
)
def test_publication_audit_rejects_positioning_language_in_public_docs(tmp_path, relative, text, matched):
    from scripts.check_publication import audit_tree

    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Product\n{text}\n", encoding="utf-8")

    assert audit_tree(tmp_path, [relative]) == [f"positioning language in {relative.as_posix()}: {matched}"]


def test_publication_audit_allows_benign_resume_reviewer_and_cv_usage(tmp_path):
    from scripts.check_publication import audit_tree

    readme = tmp_path / "README.md"
    readme.write_text(
        "Processing can resume after interruption. "
        "A reviewer checks the release evidence. "
        "The report can include a coefficient of variation (CV).\n",
        encoding="utf-8",
    )

    assert audit_tree(tmp_path, [Path("README.md")]) == []


def test_publication_audit_reports_windows_home_path(tmp_path):
    from scripts.check_publication import audit_tree

    windows_home = "C:" + "\\" + r"Users\alice\file.txt\n"
    (tmp_path / "README.md").write_text(windows_home)
    assert audit_tree(tmp_path, [Path("README.md")]) == ["absolute user path: README.md"]
