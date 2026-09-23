# Data and Limitations

This is research software, not investment advice. Its outputs explain calculations under explicit assumptions; they are not personalized recommendations or promises of future performance.

## Public Demo

All demo return, FX, inflation, and reference values are repository-authored synthetic values, not market history. Date labels and market-like conventions do not make them observed historical data. The [deterministic generator](../scripts/generate_demo_bundle.py), [manifest](../examples/demo/manifest.json), and [demo data license](../examples/demo/DATA_LICENSE.md) establish their origin.

The [example report](../reports/example/benchmark.md) and [overview chart](../assets/benchmark-overview.png) are illustrative synthetic-demo output. They demonstrate purchasing-power views, provenance, and limitations; they should not be used to compare actual investments. Synthetic reference rows test the evidence workflow, not independent market-source accuracy.

The default benchmark path rejects synthetic inputs. `--allow-synthetic-demo` explicitly enables the demo while preserving `data_kind: synthetic_test`, incomplete readiness, and the requirement for production data. [Demo tests](../tests/test_demo.py) cover rejection, opt-in, and input tampering.

## Redistribution Boundary

| Material | Terms and boundary |
|---|---|
| Source code | [MIT license](../LICENSE) |
| Repository-authored demo values | [CC0-1.0 dedication](../examples/demo/DATA_LICENSE.md) |
| Third-party or raw inputs | Retain their original terms; licensed/raw files are user-supplied and are not redistributed in this public bundle |

Public adapters and builders describe how to process supported formats. Their presence grants no access or redistribution rights to source workbooks, downloaded datasets, documents, or service responses. Users must obtain their own inputs and check applicable terms before sharing derived material. The code license does not relicense third-party data.

Local holdings, account balances, planning context, and raw source caches are outside the public artifact set. [Ignore rules](../.gitignore) and the [publication audit](../scripts/check_publication.py) support this boundary; manual review is still required.

## Known Limitations

The nine-core-asset US/mainland China/Hong Kong milestone is incomplete. The [checked-in report](../reports/example/benchmark.md) shows missing core assets and incomplete readiness; [readiness tests](../tests/test_benchmark.py) prevent a smaller declared coverage set from satisfying the fixed core universe. That report demonstrates the public demo's coverage only, not a current inventory of privately obtained market series.

The implementation's readiness condition requires market data for the full core universe and at least 10 shared complete years, as covered by [benchmark tests](../tests/test_benchmark.py). Even that condition is a dataset milestone, not certification for live use. Candidate sources cannot enter benchmark results, and the system does not silently substitute a proxy. [Qualification tests](../tests/test_market_data.py) cover selected-series rejection and reference matching; source independence and methodology suitability remain review responsibilities.

Annual rebalancing and year-end observations simplify the analysis. Drawdown does not capture intra-year extremes; short histories leave long-horizon metrics unavailable. Fees depend on declared per-series treatment. The synthetic demo does not model taxes or transaction costs. See the [report assumptions](../reports/example/benchmark.md) and [evaluation guide](evaluation.md).

The optimizer accepts supplied return tables and performs a heuristic search; benchmark data qualification is not automatically applied to that separate command. An optimized historical allocation is not an out-of-sample result, a guaranteed global optimum, or a feasible trade plan.

Taxes, live trading, account feasibility, and personalized recommendations are outside scope. The product does not determine brokerage eligibility, transferability, account-specific restrictions, or whether a portfolio is suitable for an individual. A web application, live execution service, and hosted account system are also outside this repository's current product boundary.

For the engineering rationale, see [architecture](architecture.md), [source qualification decisions](decisions/002-fail-closed-data-qualification.md), and [AI validation evidence](ai-assisted-development.md).
