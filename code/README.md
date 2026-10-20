# Code

The scripts run on Python 3.14 with the packages in `requirements.txt`. They were written for the database
folder layout, not for this release layout. To rerun them, rebuild that layout first:

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

Raw Electricity Authority inputs are in `data/raw/`. Unzip the four archives into the database folder:
they create `EA_EMI_raw/` (generation, grid import and high-voltage direct current link files) and
`EA data/` (plant list and Network Supply Points tables). The MBIE workbooks and the other small inputs
are included next to the scripts that read them.

## Run order

1. Historical, generation basis (`generation_pipeline/`): `build_ef_timeseries.py` and
   `build_ef_timeseries_daily_hourly.py`. Then `validate_ef_database_2015_2025.py` runs the reliability checks.
2. Historical, consumption basis (`Consumption_Island/`): `build_hvdc_transfer_full.py`,
   `build_consumption_ef_timeseries.py`, `build_consumption_ef_daily_hourly.py`.
3. Projection, Modules 1 to 7 (`edgs_pipeline/`): `build_edgs_annual_targets.py`,
   `build_edgs_plant_register.py`, `build_edgs_merit_order.py`, `build_edgs_hourly_shape.py`,
   `build_edgs_dispatch.py`, `build_edgs_reconcile_and_readme.py`, `build_edgs_island_consumption.py`.
   The primary variant follows: `build_edgs_consistent_scope.py`, then `build_edgs_primary_hourly.py`.
   The other `build_edgs_*.py` scripts are sensitivity and diagnostic tests.
4. Validation (`docs/validation/`): `run_ipcc_uncertainty_montecarlo.py`, and the other `run_*`, `build_*`
   and `test_*` scripts.
5. Paper analysis (`code/paper/`), run in a copy of the database:
   - `p03_build_primary_inputs.py <copy_root>`
   - `p03_eui_all_ni_cities.py <copy_root>`, which needs the confidential NABERSNZ file. Its output is the
     released `phase3_eui_derived_v2.csv`.
   - `p03_run_chain.py <copy_root> <python>`
   - `p03_new_analyses.py`, `p03_six_order_sensitivity.py`, `p03_temporal_by_year.py`, `p03_build_supplement.py`
6. Figures and tables (`code/figures/`): `build_fig*.py` and `build_table*.py`.

Some figure and paper scripts contain the author's local paths. Edit them to point at your copy.
`build_fig2_prisma.py` and `build_fig3_disclosure.py` read the review extraction workbook, which is not
released. The coding they produce is in `data/literature_review/`.
