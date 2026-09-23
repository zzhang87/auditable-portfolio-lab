# Architecture

## Product Boundary

Auditable Portfolio Lab is a command-line research tool for fixed-allocation benchmarks, portfolio metrics, constrained optimization, and local portfolio versioning. Its central output is an inspectable result with assumptions and provenance. It is research software, not investment advice; see [data and limitations](data-and-limitations.md).

The public demonstration uses repository-authored synthetic values. It exercises the product workflow without establishing historical performance or market-data readiness. The [checked-in demo report](../reports/example/benchmark.md) and [demo tests](../tests/test_demo.py) expose that boundary.

## Data Flow

```text
Source adapters / user-supplied imports
    -> manifest + checksums
    -> qualification and validation
    -> normalized dataset
    -> currency and inflation conversion
    -> metrics / fixed-allocation benchmark
    -> report + provenance

Prepared return table -> GeneticOptimizer -> result + local version history
```

The optimizer is a separate consumer of prepared returns. Its command does not automatically run the manifest-backed benchmark pipeline; callers must establish their input basis. The [CLI](../pcopt/cli.py) exposes these distinct paths.

## Component Boundaries

### Data acquisition and import

[Source adapters](../pcopt/market_sources/) parse supported source formats; import scripts can build local datasets from user-supplied inputs. Acquisition is separate from offline evaluation. Keeping an adapter in the repository does not grant redistribution rights for the data it reads. [Adapter tests](../tests/test_market_sources.py) check parsing and input conventions.

### Dataset identity and validation

[Market dataset loading and building](../pcopt/market_data.py) validate manifests, input and evidence checksums, series metadata, and reference observations before returning normalized tables. Selected candidate series are rejected. Built bundles record a qualification cutoff and use relative file references; conflicting immutable destinations require a new output directory. [Data tests](../tests/test_market_data.py) and [builder tests](../tests/test_market_cli.py) cover these guarantees.

Checksums establish content identity, not economic truth. Source choice, reference independence, methodology, and permissions still require review.

### Currency and inflation conversion

[Currency helpers](../pcopt/currency.py) select common observed year-end FX endpoints, convert local nominal returns into the requested base currency, and deflate with that currency's December-over-December CPI changes. The benchmark aligns a common complete interval for both purchasing-power views. Missing, stale, or inconsistent inputs fail validation rather than being silently filled. [Currency tests](../tests/test_currency.py) and [benchmark tests](../tests/test_benchmark.py) include hand-checked conversions and interval boundaries.

### Metrics and optimization

[Metrics](../pcopt/metrics.py) operate on return sequences. [Benchmark evaluation](../pcopt/benchmark.py) applies fixed weights with annual rebalancing and keeps nominal and real results explicit. [GeneticOptimizer](../pcopt/optimizer.py) searches allocations using supplied returns, objectives, constraints, and a random seed. It does not acquire data or perform FX conversion.

Optimization is heuristic: the returned result includes feasibility, and callers must inspect it. A result is not a proof of a global optimum or of account-level implementability. [Optimizer tests](../tests/test_optimizer.py) cover constraints and persistence; [storage tests](../tests/test_storage.py) cover local version lineage.

### Reporting and provenance

The [report writer](../pcopt/benchmark.py) produces Markdown, JSON, and an artifact-checksum sidecar. Reports expose the selected years, series, weights, FX endpoints, inflation observations, exclusions, availability, and readiness. They expose unavailable metrics instead of fabricating them. [Replay handling](../pcopt/replay.py) records commands with portable paths and marks redacted external-path templates non-runnable. The [optional chart renderer](../pcopt/visualization.py) consumes the report; it does not perform source acquisition or change qualification.

## Failure Model

The manifest-backed workflow rejects checksum mismatches, candidate series, malformed metadata, invalid weights, internal gaps, and unsupported explicit intervals. Synthetic loading and report writing require explicit demo opt-in. These are covered by [data](../tests/test_market_data.py), [benchmark](../tests/test_benchmark.py), and [demo](../tests/test_demo.py) tests.

Not every limitation is an exception: insufficient horizons become explicit unavailable metrics, and incomplete core coverage becomes an incomplete readiness result. A successful command therefore does not imply a completed market-data milestone. See [evaluation](evaluation.md).

## Reproducibility Contract

Reproduction depends on the same input bytes, manifest identity, explicit cutoff, portfolio definitions, and calculation settings. [CLI tests](../tests/test_market_cli.py) cover relocation, clock-independent cutoffs, recorded command replay, and byte-identical repeated reports in controlled conditions. [Demo verification](../pcopt/demo.py) compares semantic fields including provenance and readiness, then checks actual report bytes against their sidecar. Replay-path fields are excluded from semantic comparison and have [separate tests](../tests/test_replay.py).

This contract does not assert byte-identical outputs for arbitrary dependency versions or validate a source's financial claims. The [evaluation guide](evaluation.md) provides the runnable checks; the [AI development cases](ai-assisted-development.md) explain how these acceptance boundaries shaped implementation.
