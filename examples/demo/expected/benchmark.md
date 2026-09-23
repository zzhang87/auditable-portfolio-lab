# Fixed-allocation benchmark report

Dataset: `ce5602c8dcf46be0c3f60d35884312a7935e4b2cbb9a5436b6c950fb41d77522`  
Evaluation years: 2015–2025 (11 complete annual observations)  
Risk sampling: Year-end risk from annual observations.  
Readiness: **incomplete**

## Portfolio definitions

| Portfolio | Weights | Series IDs |
|---|---|---|
| balanced_demo | DEMO-DEFENSIVE: 40.00%; DEMO-GROWTH: 60.00% | DEMO-DEFENSIVE: DEMO-DEFENSIVE-TR; DEMO-GROWTH: DEMO-GROWTH-TR |

## USD purchasing-power view

| Portfolio | Nominal cumulative return | Real cumulative return | Nominal CAGR | Real CAGR | Real volatility | Deepest drawdown | Ulcer index |
|---|---:|---:|---:|---:|---:|---:|---:|
| balanced_demo | 45.23% | 5.74% | 3.45% | 0.51% | 7.74% | -19.76% | 9.47% |

### Horizon metrics

| Portfolio | Windows (10y / 20y / 30y) | Rolling CAGR min / 15th / median / 85th / max | Start-date sensitivity | SWR / PWR / LTWR |
|---|---|---|---|---|
| balanced_demo | 10y: 2; 20y: 0; 30y: 0 | 0.00% / 0.05% / 0.16% / 0.27% / 0.32% | Unavailable: insufficient complete annual observations (11/20 years) | Unavailable: insufficient complete annual observations (11/30 years) |

Rolling CAGR values are min / 15th percentile / median / 85th percentile / max. Withdrawal values are SWR / PWR / LTWR. Windows are overlapping.

## CNY purchasing-power view

| Portfolio | Nominal cumulative return | Real cumulative return | Nominal CAGR | Real CAGR | Real volatility | Deepest drawdown | Ulcer index |
|---|---:|---:|---:|---:|---:|---:|---:|
| balanced_demo | 65.87% | 41.63% | 4.71% | 3.21% | 5.77% | -6.49% | 2.01% |

### Horizon metrics

| Portfolio | Windows (10y / 20y / 30y) | Rolling CAGR min / 15th / median / 85th / max | Start-date sensitivity | SWR / PWR / LTWR |
|---|---|---|---|---|
| balanced_demo | 10y: 2; 20y: 0; 30y: 0 | 2.52% / 2.67% / 3.04% / 3.40% / 3.55% | Unavailable: insufficient complete annual observations (11/20 years) | Unavailable: insufficient complete annual observations (11/30 years) |

Rolling CAGR values are min / 15th percentile / median / 85th percentile / max. Withdrawal values are SWR / PWR / LTWR. Windows are overlapping.

## FX and inflation provenance

FX metadata: observation_timing: synthetic year-end observation; quote_orientation: units_per_USD; series: CNY: synthetic; HKD: synthetic

| Endpoint year | Observed date | CNY per USD | HKD per USD |
|---:|---|---:|---:|
| 2014 | 2014-12-31 | 6.12 | 7.75 |
| 2015 | 2015-12-31 | 6.49 | 7.75 |
| 2016 | 2016-12-31 | 6.94 | 7.75 |
| 2017 | 2017-12-31 | 6.51 | 7.81 |
| 2018 | 2018-12-31 | 6.88 | 7.83 |
| 2019 | 2019-12-31 | 6.96 | 7.79 |
| 2020 | 2020-12-31 | 6.53 | 7.75 |
| 2021 | 2021-12-31 | 6.37 | 7.8 |
| 2022 | 2022-12-31 | 6.9 | 7.8 |
| 2023 | 2023-12-31 | 7.1 | 7.81 |
| 2024 | 2024-12-31 | 7.3 | 7.77 |
| 2025 | 2025-12-31 | 6.99 | 7.78 |

Inflation metadata: CNY: basis: December-over-December; geography: China; seasonal_adjustment: not seasonally adjusted; units: decimal_change; USD: basis: December-over-December; geography: United States; seasonal_adjustment: not seasonally adjusted; units: decimal_change

USD selected CPI changes: 2015: 0.1000%; 2016: 2.1000%; 2017: 2.1000%; 2018: 1.9000%; 2019: 2.3000%; 2020: 1.4000%; 2021: 7.0000%; 2022: 6.5000%; 2023: 3.4000%; 2024: 2.9000%; 2025: 2.7000%
CNY selected CPI changes: 2015: 1.6000%; 2016: 2.1000%; 2017: 1.8000%; 2018: 1.9000%; 2019: 4.5000%; 2020: 0.2000%; 2021: 1.5000%; 2022: 1.8000%; 2023: -0.3000%; 2024: 0.1000%; 2025: 0.8000%

## Dataset assumptions

- Synthetic demonstration data; not historical market evidence
- Annual rebalancing; taxes and transaction costs are not modeled

## Coverage and readiness

| Field | Value |
|---|---|
| complete_shared_years | 11 |
| first_complete_year | 2015 |
| latest_complete_year | 2025 |
| minimum_shared_years | 10 |
| required_assets | DEMO-GROWTH; DEMO-DEFENSIVE |
| scope | Synthetic product demonstration only |
| Missing core assets | CHN-A-CSI300; CHN-CASH; CHN-GOV; GLO-GLD; HKG-HSCEI; HKG-HSI; USA-BIL; USA-ITT; USA-LCB |
| Full core universe shared years | 0 / 10 required |

## Source, fee, and backfill caveats

| Asset | Source | Fee basis | Fee notes | Backfill | Limitations |
|---|---|---|---|---|---|
| DEMO-DEFENSIVE | REPOSITORY-AUTHORED-SYNTHETIC-DEMO | gross_of_fund_fees | No fees; repository-authored synthetic demonstration series | none declared | Synthetic demonstration data; not historical market evidence |
| DEMO-GROWTH | REPOSITORY-AUTHORED-SYNTHETIC-DEMO | gross_of_fund_fees | No fees; repository-authored synthetic demonstration series | none declared | Synthetic demonstration data; not historical market evidence |

## Excluded years

None.

## Regeneration

`pcopt benchmark --manifest examples/demo/manifest.json --weights examples/demo/portfolio.json --base-currency both --output-dir examples/demo/expected --as-of 2026-01-01 --allow-synthetic-demo`
