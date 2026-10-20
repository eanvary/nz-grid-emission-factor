# Data

All times are New Zealand local time, as recorded in the source data. Hourly rows are clock hours:
the day clocks go forward (last Sunday of September) has no 02:00 row, and on the day clocks go back
(first Sunday of April) the 02:00 row holds both runs of that hour. NI is the North Island and SI the
South Island. The Ministry of Business, Innovation and Employment (MBIE) publishes the Electricity Demand
and Generation Scenarios (EDGS) 2024 that the projection reconstructs.

## historical/generation_basis/

These files attribute emissions to the island where electricity is generated. They are built from
Electricity Authority half-hourly metered generation, January 2015 to December 2025.

`{annual,monthly,daily,hourly}_emission_factor_NI_SI.csv`

| Column | Meaning |
|---|---|
| `island` | NI or SI |
| `year`, `month`, `period`, `date`, `hour`, `datetime` | time keys (by resolution) |
| `EF_kg_per_MWh` | emission factor, kg CO2e/MWh (equal to g CO2e/kWh) |
| `total_gen_MWh`, `total_CO2_kg` | metered generation and attributed emissions |
| `filled_gen_MWh`, `CO2_kg_estimated` | part of generation and emissions from gap-filled records |
| `*_stratford_ccgt`, `*_stratford_peaker` | bound with Stratford attributed at its combined-cycle or its peaker record |
| `*_glenbrook_gas` | bound with Glenbrook cogeneration at a gas heat rate instead of zero (see `docs/DATABASE_SPEC.md`) |

The folder also holds generation by fuel (`monthly_fuel_mix_NI_SI.csv`), plant-level totals
(`plant_level_generation_emissions_2015_2025.csv`), and data coverage (`completeness_flags.csv`,
`filled_generation_summary.csv`).

## historical/consumption_basis/

These files reallocate emissions across the high-voltage direct current (HVDC) link between the islands.
An importing island takes emissions at the exporting island's intensity. The `*_consumption_EF_NI_SI.csv`
files give `NI_EF_consumption` and `SI_EF_consumption` in kg CO2e/MWh, with the generation-basis values
alongside. The `*_hvdc_transfer_NI_SI.csv` files give the transfer in each direction.

## historical/validation/

`DATA_QUALITY_ASSESSMENT_RESULTS.csv` holds the results of the database reliability checks.
`D3_fuel_level_validation.csv` compares fuel use with MBIE statistics. The `detail/` folder holds the em6
cross-check and the Monte Carlo uncertainty summaries (IPCC Approach 2, 50,000 trials).

## projection/

The projection covers the five MBIE EDGS 2024 scenarios (Constraint, Environmental, Growth, Innovation,
Reference), hourly from 2024 to 2050. The headline files use template year 2021:
`edgs_hourly_emission_factor_generation.parquet` and `edgs_hourly_emission_factor_consumption.parquet`.
The template-year sensitivity files, `edgs_hourly_emission_factor_tmpl{2017,2023,2024}.parquet`, hold both
bases in one file.

| Column | Meaning |
|---|---|
| `scenario` | MBIE EDGS 2024 scenario |
| `island` | NI, SI, or National |
| `datetime_hour` | start of the hour |
| `ef_basis` | `generation` or `consumption`; the National factor is stored under `consumption` and is the national grid-basis factor |
| `emission_factor_kg_co2e_per_kwh` | emission factor, kg CO2e/kWh |
| `reconciliation_flag` | `PRIMARY`: consistent scope, grid-injection basis |

The analysis scripts read the two headline files as one. To rebuild it:

```python
import pandas as pd
pd.concat([pd.read_parquet(f"edgs_hourly_emission_factor_{b}.parquet") for b in ("consumption", "generation")]) \
  .to_parquet("edgs_hourly_emission_factor.parquet", index=False)
```

The row order differs from the original file, and the values are identical. The original file is in the
data deposit.

Other projection files:

- `edgs_hourly_island_load_primary.parquet`: island load, used as consumption weights.
- `consistent_scope/annual_ef_by_variant.csv`: annual factors by scope variant. The paper uses
  `variant == "consistent_scope"` and the `EF_*_grid` columns.
- `edgs_annual_targets.csv`: the MBIE annual totals the reconstruction is scaled to.
- Plant register, merit order, thermal intensity and hourly shape tables.

## raw/

The Electricity Authority files the database was built from, as published on Electricity Market
Information (EMI) when the database was built. EMI revises its datasets, so a fresh download can differ
from these copies.

| Archive | Contents |
|---|---|
| `ea_emi_generation_md.zip` | `EA_EMI_raw/YYYYMM_Generation_MD.csv`, half-hourly metered generation, January 2015 to December 2025 |
| `ea_emi_grid_import.zip` | `EA_EMI_raw/YYYYMM_Grid_import.csv`, half-hourly grid import by point of connection, used for the flagged fills |
| `ea_emi_hvdc_flows.zip` | `EA_EMI_raw/YYYYMM_HVDC_flows.csv`, half-hourly flows on the HVDC link |
| `ea_reference_tables.zip` | `EA data/Dispatched generation plant.csv` and `EA data/NSP Tables/` (point of connection to island lookup) |

Unzip all four into the database folder; the paths inside the archives match what the scripts read.

## analysis_tables/ and paper_results/

These folders hold the intermediate and final tables of the paper's analysis. They include load profiles,
decomposition results and sensitivity tests. The numbers quoted in the paper are in
`paper_results/numbers_for_text.json`. The aggregated NABERSNZ cohort statistics are in
`analysis_tables/phase3_eui_derived_v2.csv` (n, 10th percentile, median, 90th percentile). No
building-level values are released.

## literature_review/

Coding of the reviewed assessments behind Figures 1, 3 and 8 of the paper.

## Sources

| Source | Used for | Licence |
|---|---|---|
| Electricity Authority, Electricity Market Information: Generation_MD, Grid_import, HVDC flows, dispatched generation plant list, Network Supply Points tables, https://www.emi.ea.govt.nz | historical database, hourly shapes | CC BY 4.0 |
| MBIE, Electricity Demand and Generation Scenarios 2024 (results and assumptions workbooks) | projection | CC BY 4.0 |
| MBIE, quarterly electricity emissions workbook and gas data tables | validation | CC BY 4.0 (MBIE's electricity statistics page states CC BY 3.0 New Zealand) |
| Ministry for the Environment, measuring emissions guidance, emission factors 2025 | combustion factors | CC BY 4.0 |
| em6 carbon service | validation | see provider terms |
| Building Data Genome 2 (Miller et al., 2020) | real-building sensitivity | CC BY 4.0 |

Electricity Authority material is credited as "www.emi.ea.govt.nz provided by the Electricity Authority
(New Zealand)", as the Authority asks. MBIE material is Crown copyright, credited to the Ministry of
Business, Innovation and Employment.
