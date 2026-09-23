# Decision: Fail Closed on Data Qualification

## Context

Similar-looking series can differ in return basis, fees, currency, coverage, and methodology. A successful import or matching checksum does not establish suitability for a benchmark.

## Decision

Candidate data cannot enter benchmark results. Require validated selected-series metadata, checksums, and matching reference evidence; reject invalid inputs instead of weakening the contract. The synthetic sample requires explicit opt-in and retains its non-market identity. [Data tests](../../tests/test_market_data.py) and [sample tests](../../tests/test_demo.py) are the executable acceptance evidence.

## Consequences

Unqualified inputs remain unavailable, so coverage can remain incomplete. Source review and redistribution checks remain human responsibilities: checksums validate content identity, and reference agreement does not prove independence. The [data boundary](../data-and-limitations.md) and [example report](../../reports/example/benchmark.md) expose these limits. This qualification gate belongs to the manifest-backed benchmark workflow; the separate optimizer accepts prepared returns.

## Rejected alternatives

- Silent proxy substitution: it changes the economic question while making coverage appear complete.
- Promoting an imported candidate or a synthetic fixture to market data: structural validity alone is not source qualification.
- Concealing missing coverage behind a successful command: execution success is distinct from dataset readiness.
