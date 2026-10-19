# Data

All times are New Zealand local time as recorded in the source data. NI = North Island, SI = South Island.

## historical/generation_basis/

Emissions attributed to the island where electricity is generated, from Electricity Authority half-hourly
metered generation, January 2015 to August 2026.

`{annual,monthly,daily,hourly}_emission_factor_NI_SI.csv`

| Column | Meaning |
|---|---|
| `island` | NI or SI |
| `year`, `month`, `period`, `date`, `hour`, `datetime` | time keys (by resolution) |
| `EF_kg_per_MWh` | emission factor, kg CO2e/MWh (equal to g CO2e/kWh) |
| `total_gen_MWh`, `total_CO2_kg` | metered generation and attributed emissions |
| `filled_gen_MWh`, `CO2_kg_estimated` | part of generation and emissions from gap-filled records |
| `*_stratford_ccgt`, `*_stratford_peaker` | bound with Stratford attributed at its combined-cycle or its peaker record |
| `*_glenbrook_gas` | bound with Glenbrook cogeneration at a gas heat rate instead of zero (see `docs/DATABASE_SPEC.md`, section 2) |

Also: `monthly_fuel_mix_NI_SI.csv` (generation by fuel), `plant_level_generation_emissions_2015_2025.csv`,
`completeness_flags.csv` and `filled_generation_summary.csv` (data coverage).

## historical/consumption_basis/

Emissions reallocated across the HVDC link: an importing island takes emissions at the exporting island's
intensity. `*_consumption_EF_NI_SI.csv` give `NI_EF_consumption`, `SI_EF_consumption` (kg CO2e/MWh) with the
generation-basis values alongside; `*_hvdc_transfer_NI_SI.csv` give transfer in each direction.

## historical/validation/

Results of the database reliability checks (`DATA_QUALITY_ASSESSMENT_RESULTS.csv`), the fuel-level comparison
with MBIE statistics (`D3_fuel_level_validation.csv`), and in `detail/` the em6 cross-check and the Monte Carlo
uncertainty summaries (IPCC Approach 2, 50,000 trials).

## projection/

MBIE EDGS 2024 scenarios (Constraint, Environmental, Growth, Innovation, Reference), 2024 to 2050, hourly.

`edgs_hourly_emission_factor_generation.parquet`, `edgs_hourly_emission_factor_consumption.parquet`
(headline, template year 2021) and `edgs_hourly_emission_factor_tmpl{2017,2023,2024}.parquet` (template-year
sensitivity, both bases in one file)

| Column | Meaning |
|---|---|
| `scenario` | MBIE EDGS 2024 scenario |
| `island` | NI, SI, or National |
| `datetime_hour` | start of the hour |
| `ef_basis` | `generation` or `consumption`; the National factor is stored under `consumption` and is the national grid-basis factor |
| `emission_factor_kg_co2e_per_kwh` | emission factor, kg CO2e/kWh |
| `reconciliation_flag` | `PRIMARY`: consistent scope, grid-injection basis |

To rebuild the single file the analysis scripts read:

```python
import pandas as pd
pd.concat([pd.read_parquet(f"edgs_hourly_emission_factor_{b}.parquet") for b in ("consumption", "generation")]) \
  .to_parquet("edgs_hourly_emission_factor.parquet", index=False)
```

Row order differs from the original file; values are identical. The original file is in the data deposit.

Also: `edgs_hourly_island_load_primary.parquet` (island load used as consumption weights),
`consistent_scope/annual_ef_by_variant.csv` (annual factors by scope variant; the paper uses
`variant == "consistent_scope"`, columns `EF_*_grid`), `edgs_annual_targets.csv` (MBIE annual totals the
reconstruction is scaled to), plant register, merit order, thermal intensity and hourly shape tables.

## analysis_tables/ and paper_results/

Intermediate and final tables of the paper's analysis: load profiles, decomposition results, sensitivity
tests, and the numbers quoted in the text (`paper_results/numbers_for_text.json`).
`analysis_tables/phase3_eui_derived_v2.csv` holds the aggregated NABERSNZ cohort statistics (n, 10th
percentile, median, 90th percentile); no building-level values are released.

## literature_review/

Coding of the reviewed assessments behind Figures 1, 3 and 8 of the paper.

## Sources

| Source | Used for | Licence |
|---|---|---|
| Electricity Authority, Electricity Market Information (EMI): generation output by plant, HVDC flows, Network Supply Points table, https://www.emi.ea.govt.nz | historical database, hourly shapes | CC BY 4.0 |
| MBIE, Electricity Demand and Generation Scenarios 2024 (results and assumptions workbooks) | projection | CC BY 4.0 |
| MBIE, quarterly electricity emissions and energy statistics | validation | CC BY 4.0 |
| Ministry for the Environment, measuring emissions guidance, emission factors 2025 | combustion factors | CC BY 4.0 |
| em6 carbon service | validation | see provider terms |
| Building Data Genome 2 (Miller et al., 2020) | real-building sensitivity | CC BY 4.0 |
