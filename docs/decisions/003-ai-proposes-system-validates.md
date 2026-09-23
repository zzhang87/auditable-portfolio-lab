# Decision: AI Proposes, the System Validates

## Context

AI can help explore sources, implement calculations, and identify review issues. Plausible output can still contain incorrect assumptions, omit edge cases, or obscure provenance.

## Decision

AI may propose research, code, and review findings. Tests, checksums, source checks, reproducible artifacts, and human-approved scope decide acceptance. The operating model is: AI supports exploration, implementation, and review; explicit requirements, deterministic checks, and reproducible artifacts decide what is accepted.

## Consequences

Translate accepted findings into inspectable behavior: [metric regressions](../../tests/test_metrics.py), [qualification tests](../../tests/test_market_data.py), and [replay tests](../../tests/test_market_cli.py). Keep contribution and validation boundaries explicit in the [AI case studies](../ai-assisted-development.md). Automated checks cannot certify source independence, investment suitability, or the causal productivity impact of AI; the repository claims none of those outcomes.

## Rejected alternatives

- Treating a confident AI explanation or review verdict as sufficient acceptance evidence.
- Claiming the product was built independently by AI or attributing unmeasured productivity gains to AI.
- Using prompt dumps or fabricated historical review records in place of executable evidence.
