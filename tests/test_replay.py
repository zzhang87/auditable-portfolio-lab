from argparse import Namespace
from pathlib import Path


def test_display_path_preserves_relative_and_relativizes_internal_absolute(tmp_path):
    from pcopt.replay import display_path

    assert display_path(Path("examples/demo/manifest.json"), tmp_path) == (
        "examples/demo/manifest.json",
        True,
    )
    internal = tmp_path / "examples" / "demo" / "manifest.json"
    assert display_path(internal, tmp_path) == ("examples/demo/manifest.json", True)


def test_display_path_redacts_external_absolute_path(tmp_path):
    from pcopt.replay import display_path

    rendered, runnable = display_path(Path("/private/input/manifest.json"), tmp_path)
    assert rendered == "<external>/manifest.json"
    assert runnable is False
    assert "/private/input" not in rendered


def test_build_replay_preserves_automatic_boundaries(tmp_path):
    from pcopt.replay import build_replay

    args = Namespace(
        manifest=Path("examples/demo/manifest.json"),
        weights=Path("examples/demo/portfolio.json"),
        base_currency="both",
        output_dir=Path("reports/example"),
        start_year=None,
        end_year=None,
        allow_synthetic_demo=True,
    )
    replay = build_replay(args, "2026-01-01", tmp_path)
    assert replay["argv"][0:4] == ["pcopt", "benchmark", "--manifest", "examples/demo/manifest.json"]
    assert "--start-year" not in replay["argv"]
    assert "--end-year" not in replay["argv"]
    assert "--allow-synthetic-demo" in replay["argv"]
    assert replay["runnable"] is True
