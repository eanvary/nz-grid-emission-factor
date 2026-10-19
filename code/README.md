# Code

Python 3.14 with the packages in `requirements.txt`. The scripts were written for the database folder
layout, not this release layout. To rerun them, rebuild that layout first:

| Release folder | Database folder |
|---|---|
| `code/generation_pipeline/` | `generation_pipeline/` |
| `code/consumption_pipeline/` | `Consumption_Island/` |
| `code/projection_pipeline/` | `edgs_pipeline/` |
| `code/validation/` | `docs/validation/` |
| `code/analysis/` | `analysis_paper/scripts/` |
| `code/analysis/bdg2_sensitivity/` | `analysis_paper/sensitivity_realdata_bdg2/scripts/` |
| `data/historical/generation_basis/`, `data/historical/validation/*.csv` | `output/` |
| `data/historical/consumption_basis/` | `Consumption_Island/output/` |
| `data/projection/` | `output/edgs/` |
| `data/analysis_tables/` | `analysis_paper/tables/` |

Raw inputs go in `EA_EMI_raw/` (EMI generation and HVDC files), `EA data/` (dispatched generation plant
list and Network Supply Points tables), and the two MBIE EDGS 2024 workbooks in `edgs_pipeline/`.
Sources are listed in `data/README.md`.

## Run order

1. Historical, generation basis (`generation_pipeline/`): `build_ef_timeseries.py`,
   `build_ef_timeseries_daily_hourly.py`, then `validate_ef_database_2015_2025.py` (reliability checks).
2. Historical, consumption basis (`Consumption_Island/`): `build_hvdc_transfer_full.py`,
   `build_consumption_ef_timeseries.py`, `build_consumption_ef_daily_hourly.py`.
3. Projection (`edgs_pipeline/`), Modules 1 to 7: `build_edgs_annual_targets.py`, `build_edgs_plant_register.py`,
   `build_edgs_merit_order.py`, `build_edgs_hourly_shape.py`, `build_edgs_dispatch.py`,
   `build_edgs_reconcile_and_readme.py`, `build_edgs_island_consumption.py`; then the primary variant,
   `build_edgs_consistent_scope.py` and `build_edgs_primary_hourly.py`.
   The remaining `build_edgs_*.py` scripts are sensitivity and diagnostic tests.
4. Validation (`docs/validation/`): `run_ipcc_uncertainty_montecarlo.py` and the other `run_*`, `build_*`
   and `test_*` scripts.
5. Paper analysis, in a copy of the database (`code/paper/`):
   `p03_build_primary_inputs.py <copy_root>`, `p03_eui_all_ni_cities.py <copy_root>` (needs the confidential
   NABERSNZ file; the released `phase3_eui_derived_v2.csv` is its output), `p03_run_chain.py <copy_root> <python>`,
   then `p03_new_analyses.py`, `p03_six_order_sensitivity.py`, `p03_temporal_by_year.py` and
   `p03_build_supplement.py`.
6. Figures (`code/figures/`): `build_fig*.py` and `build_table*.py`.

Some figure and paper scripts contain the author's local paths; edit them to point at your copy.
`build_fig2_prisma.py` and `build_fig3_disclosure.py` read the review extraction workbook, which is not
released; the coding they produce is in `data/literature_review/`.
