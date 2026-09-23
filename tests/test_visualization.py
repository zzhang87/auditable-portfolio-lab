from pathlib import Path


def test_visualization_module_is_lazy_and_writes_png(tmp_path):
    from pcopt.visualization import render_benchmark_overview

    output = render_benchmark_overview(
        Path("examples/demo/expected/benchmark.json"),
        tmp_path / "overview.png",
    )
    assert output == tmp_path / "overview.png"
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output.stat().st_size > 20_000


def test_core_import_does_not_load_matplotlib():
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-c", "import pcopt, sys; print('matplotlib' in sys.modules)"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "False"
