# Evaluation

Evaluation checks calculation invariants, data boundaries, and reproducible outputs. It does not establish investment suitability, future returns, or completion of the market-data milestone. The [example report](../reports/example/benchmark.md) is illustrative synthetic-demo output and explicitly reports incomplete readiness.

## Test Layers

| Layer | What the evidence establishes | Checked-in evidence |
|---|---|---|
| Unit invariants | Initial-wealth drawdown, annual rebalancing, currency direction, inflation adjustment, and constraint boundaries | [Metrics](../tests/test_metrics.py), [currency](../tests/test_currency.py), [optimizer](../tests/test_optimizer.py) |
| Qualification | Rejection of candidate metadata, wrong return conventions, altered files, and invalid reference evidence | [Market data](../tests/test_market_data.py), [source adapters](../tests/test_market_sources.py) |
| Integration and CLI | Relocatable dataset builds, explicit cutoffs, command replay, report creation, and local version persistence | [Market CLI](../tests/test_market_cli.py), [benchmark](../tests/test_benchmark.py), [storage](../tests/test_storage.py) |
| Demo semantic replay | Synthetic opt-in, tamper rejection, semantic equivalence, required artifacts, and report checksums | [Demo](../tests/test_demo.py) |
| Presentation | PNG generation, required currency views, portfolio selection, and aligned years | [Visualization](../tests/test_visualization.py) |
| Publication audit | Forbidden tracked paths, known private-path patterns, removed positioning language, and broken relative Markdown file links | [Publication](../tests/test_publication.py) |

### Demo semantic replay

After installing the package and development dependencies, run from the repository root with an unused output directory:

```bash
python -m pcopt.cli benchmark \
  --manifest examples/demo/manifest.json \
  --weights examples/demo/portfolio.json \
  --base-currency both \
  --output-dir reports/local-demo \
  --as-of 2026-01-01 \
  --allow-synthetic-demo
python scripts/verify_demo.py \
  --expected examples/demo/expected \
  --actual reports/local-demo
```

The cutoff above reproduces the illustrative synthetic [expected report](../examples/demo/expected/benchmark.json). The workflow reads checked-in inputs without requiring a network. Explicit synthetic opt-in does not turn the data into market history or make readiness complete; [demo tests](../tests/test_demo.py) assert both boundaries.

The [verifier](../pcopt/demo.py) compares report schema, dataset identity, data kind, evaluation, source assumptions, provenance, coverage, views, and readiness. It excludes replay display fields and checks the generated JSON and Markdown bytes against their generated checksum sidecar. [Replay tests](../tests/test_replay.py) separately check portable paths and external-path redaction. This is not a cryptographic authenticity guarantee: jointly replacing an artifact and its checksum can evade an integrity-only check, and the verifier does not independently prove source truth or compare every Markdown sentence against expected Markdown.

### Publication audit

```bash
python -m pytest tests/test_publication.py -v
python scripts/check_publication.py
```

The [audit](../scripts/check_publication.py) inspects Git-tracked files, including newly staged documents. Stage intended publication files before the final audit. It checks relative link targets as files or directories, not Markdown heading anchors or remote URLs. Human review remains necessary for sensitive content and redistribution rights; ignore rules and this scanner are not a comprehensive secrets detector.

## Release Gates

Before accepting a public revision, require:

1. The full local test suite passes: `python -m pytest`.
2. Package build and installation succeed, and both `pcopt --help` and `python -m pcopt.cli --help` work. [Packaging configuration](../pyproject.toml) defines the entry point and dependency groups.
3. The offline demo regenerates and passes semantic verification against checked-in expected artifacts.
4. The staged publication set passes the audit, and a reviewer checks source terms, claim evidence, and local-only exclusions.
5. When code or chart rendering changes, applicable lint/format checks and chart regeneration pass; visualization requires the optional `viz` dependencies.

These are acceptance requirements, not a claim that a remote CI run or every supported Python environment has already passed. Preserve run evidence for the revision being reviewed rather than treating a historical test count as current proof.

### Unavailable metrics for short horizons

The benchmark uses complete annual observations. Rolling CAGR requires 10 years, start-date sensitivity 20 years, and withdrawal metrics 30 years; [availability tests](../tests/test_benchmark.py) assert the required horizons and overlapping-window counts. Shorter histories show an unavailable status and reason rather than an invented value. Overlapping windows are not independent samples.

The illustrative synthetic [demo report](../reports/example/benchmark.md) has 11 complete annual observations, so the longer-horizon metrics remain unavailable. Annual year-end drawdown also omits intra-year losses. Neither a populated metric nor a passing test suite supplies a forecast or resolves the [known data limitations](data-and-limitations.md).
