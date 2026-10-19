# New Zealand island-resolved grid emission factors, 2015 to 2050

Data and code for the paper *Where, when, and which future: decomposing grid emission factor error in
building life cycle assessment* (Arab Anvari et al., under review).

The repository holds grid emission factors for the North Island (NI) and South Island (SI) of New Zealand:

| Part | Period | Resolution | Folder |
|---|---|---|---|
| Historical, generation basis | January 2015 to August 2026 | annual, monthly, daily, hourly | `data/historical/generation_basis/` |
| Historical, consumption basis (follows flows on the HVDC link) | as above | annual, monthly, daily, hourly | `data/historical/consumption_basis/` |
| Projection, five MBIE EDGS 2024 scenarios | 2024 to 2050 | annual and hourly; NI, SI, National | `data/projection/` |

The historical series is built from Electricity Authority half-hourly metered generation. The projection
reconstructs each MBIE Electricity Demand and Generation Scenarios (EDGS) 2024 trajectory at hourly
resolution for each island. Method, scope and validation are described in the paper, in
`docs/DATABASE_SPEC.md` and in `docs/methodology/`.

## Quick start

```python
import pandas as pd

hist = pd.read_csv("data/historical/generation_basis/hourly_emission_factor_NI_SI.csv", parse_dates=["datetime"])
proj = pd.read_parquet("data/projection/edgs_hourly_emission_factor_generation.parquet")
ni_ref_2030 = proj.query("scenario == 'Reference' and island == 'NI' and datetime_hour.dt.year == 2030")
```

Units differ between the two parts: historical files report kg CO2e/MWh (`EF_kg_per_MWh`), projection
files report kg CO2e/kWh (`emission_factor_kg_co2e_per_kwh`). Column definitions are in `data/README.md`.

## Contents

- `data/` emission factor tables and the intermediate tables the paper's results are computed from.
- `code/` the three database pipelines, the validation scripts, the paper's analysis chain and figure scripts.
  Run order is in `code/README.md`.
- `docs/` database specification and methodology documents.
- `MANIFEST.csv` size and SHA-256 of every file in the repository.
- `zenodo_manifest.csv` files too large for GitHub (hourly generation by fuel, the unsplit hourly factor, and
  validation detail). These are in the archived data deposit (DOI to be added).

## Version

Database tag `ef-database-v1.0.1` (29 September 2026), the version the paper's results are computed from.
The hourly projection files are stored with zstd compression; their values are identical to the database
files, and the headline hourly factor is split into one file per accounting basis to stay under GitHub's
file size limit.

## Data not included

- NABERSNZ office energy ratings were provided by the New Zealand Green Building Council under a data sharing
  agreement. Building-level data are confidential; only the aggregated cohort statistics used in the paper
  (`data/analysis_tables/phase3_eui_derived_v2.csv`) are released. Requests for the source data should go to NZGBC.
- Raw Electricity Authority EMI files and MBIE source workbooks are not redistributed here. Their sources are
  listed in `data/README.md`.
- The Building Data Genome 2 meter data used in the real-building sensitivity test are available from their
  authors (Miller et al., 2020); `code/analysis/bdg2_sensitivity/01_extract_sample_buildings.py` extracts the sample.

## Licence

Code: MIT (`LICENSE`). Data: Creative Commons Attribution 4.0 International (`LICENSE-DATA.md`).
Source data from the Electricity Authority and MBIE are used under their own CC BY 4.0 terms.

## Citation

Please cite the paper and this repository. Citation details are in `CITATION.cff`.

## Contact

Ehsan Arab Anvari, Auckland University of Technology.
