from pathlib import Path


def test_publication_audit_accepts_clean_tree(tmp_path):
    from scripts.check_publication import audit_tree

    (tmp_path / "README.md").write_text("# Demo\n[Architecture](docs/architecture.md)\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "architecture.md").write_text("# Architecture\n")
    assert audit_tree(
        tmp_path,
        [Path("README.md"), Path("docs/architecture.md")],
    ) == []


def test_publication_audit_reports_private_paths_content_and_broken_links(tmp_path):
    from scripts.check_publication import audit_tree

    private_home = "/" + "Users/private/project"
    local_uri = "file:" + "///" + "Users/private/data.csv"
    (tmp_path / "README.md").write_text(
        f"{private_home}\n{local_uri}\n[Missing](docs/missing.md)\n"
    )
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

    (tmp_path / "README.md").write_text(r"C:\Users\alice\file.txt\n")
    assert audit_tree(tmp_path, [Path("README.md")]) == [
        "absolute user path: README.md"
    ]
