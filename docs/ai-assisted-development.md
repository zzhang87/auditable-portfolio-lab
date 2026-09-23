# AI-Assisted Development

The product is an auditable portfolio research workflow. AI supports its development through research assistance, implementation, and review; the repository does not claim that the product was built entirely or independently by AI.

The operating model is: **AI supports exploration, implementation, and review; explicit requirements, deterministic checks, and reproducible artifacts decide what is accepted.** Human-approved scope and source review remain necessary. This repository does not claim isolated productivity gains caused by AI, measured time savings, or investment-performance improvements attributable to AI.

The cases below describe the contribution and acceptance boundary. Their evidence demonstrates the implemented behavior, not a controlled measurement of AI's causal impact. They are curated engineering cases, not prompt transcripts or invented historical pull requests.

## Source Qualification

### Problem

A plausible return series may describe the wrong index, currency, fee basis, or return convention. Successfully downloading or parsing it is insufficient evidence for a benchmark.

### AI contribution

AI assisted with identifying source candidates, comparing metadata, and implementing adapters and validation. Proposed sources and code were inputs to review; they did not establish qualification by themselves.

### Failure mode

Candidate data could be promoted prematurely, price returns could be mistaken for total returns, or a checksum could be treated as proof that the underlying financial claim was correct.

### Validation gate

The loader requires validated selected-series metadata, matching content and evidence checksums, and reference observations that agree within declared tolerances. Production series require at least three reference years, covered by `test_every_selected_production_series_requires_three_reference_years` in [data tests](../tests/test_market_data.py). Source suitability and independence of reference evidence still require human review; code can check agreement, not certify independence. Synthetic fixture evidence is not external source validation.

### Evidence

[Market-data tests](../tests/test_market_data.py) exercise accepted fixtures and rejection of candidates, price-return equity, changed bytes, and mismatched references. The [demo manifest](../examples/demo/manifest.json) and [provenance artifact](../reports/example/benchmark.provenance.json) show the inspectable structure with synthetic inputs. [Data and limitations](data-and-limitations.md) documents the incomplete market milestone and redistribution boundary.

### Lesson

Use AI to broaden exploration, then make acceptance explicit. Qualification is a contract with reviewable evidence, not confidence in a generated explanation.

## Drawdown Correction

### Problem

Starting the high-water mark at the first year-end wealth omits a loss that occurs before that first endpoint. This understates drawdown and changes the ulcer index.

### AI contribution

AI assisted implementation and review of the metric calculation and regression coverage. Acceptance depended on a hand-checkable invariant rather than agreement between generated prose and generated code.

### Failure mode

A calculation can look correct on positive-first-year examples while excluding the investor's starting wealth from its loss baseline.

### Validation gate

Include initial wealth `1.0` in the high-water mark. For the illustrative synthetic sequence of a 20% loss followed by a 10% gain, drawdowns are 20% and 12% below initial wealth. These exact expectations are asserted in `test_initial_loss_counts_in_drawdown_and_ulcer` in [metric tests](../tests/test_metrics.py). Companion cases check recovery and later high-water marks. Run the regression and full suite before accepting a metric change.

### Evidence

[Metric tests](../tests/test_metrics.py) encode the independent expected values; [the metric implementation](../pcopt/metrics.py) contains the corrected high-water-mark calculation. These files substantiate the invariant without relying on a historical commit narrative.

### Lesson

A useful review finding becomes durable when translated into a financial invariant and a regression test. It does not eliminate the need to inspect other metric assumptions, including annual sampling.

## Reproducible Artifacts

### Problem

An otherwise correct result is difficult to audit if its inputs mutate, the current date changes interval selection, or its reproduction command exposes machine-specific paths.

### AI contribution

AI helped design and implement the manifest-backed build and report workflow, replay handling, and verification tests. Acceptance rested on replayed artifacts and failure cases.

### Failure mode

Numerical results can remain unchanged while provenance or readiness changes. Comparing only returns misses that drift; comparing every display byte can incorrectly reject a relocated invocation.

### Validation gate

Use explicit cutoffs, immutable dataset destinations, input checksums, offline execution, and semantic report comparison. Compare dataset identity, evaluation, assumptions, provenance, coverage, views, and readiness; separately verify report checksums and replay-path behavior. Treat external-path templates marked non-runnable as templates that require user-supplied locations.

### Evidence

[CLI tests](../tests/test_market_cli.py) cover relocatable builds, failure preservation, explicit cutoffs, command execution, and controlled byte-identical replay. [Demo tests](../tests/test_demo.py) detect semantic changes, missing artifacts, and tampering. The [checked-in report](../reports/example/benchmark.md) is illustrative synthetic-demo output; [evaluation](evaluation.md) supplies reproduction commands and the verifier's limits.

### Lesson

Reproducibility includes meaning and lineage, not just the displayed performance values. Tests and artifacts govern acceptance; AI-generated confidence is not an additional validation gate.
