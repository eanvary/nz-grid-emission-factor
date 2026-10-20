# New Zealand island-resolved grid emission factors, 2015 to 2050

Data and code for the paper *Where, when, and which future: decomposing grid emission factor error in
building life cycle assessment* (Arab Anvari et al., under review).

The repository holds grid emission factors for the North Island (NI) and South Island (SI) of New Zealand.
The historical series is built from Electricity Authority half-hourly metered generation. The projection
reconstructs the Electricity Demand and Generation Scenarios (EDGS) 2024 of the Ministry of Business,
Innovation and Employment (MBIE) at hourly resolution for each island.

| Part | Period | Resolution | Folder |
|---|---|---|---|
| Historical, generation basis | January 2015 to August 2026 | annual, monthly, daily, hourly | `data/historical/generation_basis/` |
| Historical, consumption basis | as above | annual, monthly, daily, hourly | `data/historical/consumption_basis/` |
| Projection, five MBIE EDGS 2024 scenarios | 2024 to 2050 | annual and hourly; NI, SI, national | `data/projection/` |

The consumption basis follows the power that crosses the high-voltage direct current (HVDC) link between
the islands. Method, scope and validation are described in the paper and in `docs/DATABASE_SPEC.md`.

## Quick start

```python
import pandas as pd

hist = pd.read_csv("data/historical/generation_basis/hourly_emission_factor_NI_SI.csv", parse_dates=["datetime"])
proj = pd.read_parquet("data/projection/edgs_hourly_emission_factor_generation.parquet")
ni_ref_2030 = proj.query("scenario == 'Reference' and island == 'NI' and datetime_hour.dt.year == 2030")
```

The two parts use different units. Historical files report kg CO2e/MWh (`EF_kg_per_MWh`). Projection
files report kg CO2e/kWh (`emission_factor_kg_co2e_per_kwh`). Column definitions are in `data/README.md`.

## Contents

- `data/`: emission factor tables, and the intermediate tables behind the paper's results.
- `data/raw/`: the Electricity Authority files the database was built from, as zip archives.
- `code/`: the three database pipelines, the validation scripts, and the paper's analysis and figure
  scripts. The run order is in `code/README.md`.
- `docs/DATABASE_SPEC.md`: the database specification.
- `MANIFEST.csv`: size and SHA-256 checksum of every file in the repository.
- `zenodo_manifest.csv`: files too large for GitHub, such as hourly generation by fuel and the
  unsplit hourly factor. They are in the archived data deposit, https://doi.org/10.5281/zenodo.23487331.

## Version

The data are database tag `ef-database-v1.0.1` (29 September 2026), the version the paper's results come
from. Hourly projection files are stored with zstd compression, and their values are identical to the
database files. The headline hourly factor is split into one file per accounting basis, because a single
file exceeds GitHub's size limit.

## Data not included

- The New Zealand Green Building Council (NZGBC) provided NABERSNZ office energy ratings under a data
  sharing agreement. Building-level data are confidential. Only the aggregated cohort statistics used in the
  paper are released (`data/analysis_tables/phase3_eui_derived_v2.csv`). Requests for the source data
  should go to NZGBC.
- Two Electricity Authority file types that no pipeline reads (`Grid_export`, `Embedded_generation`) are left
  out. The raw files the pipelines do read are included in `data/raw/`.
- The Building Data Genome 2 meter data used in the real-building sensitivity test are available from their
  authors (Miller et al., 2020). The script `code/analysis/bdg2_sensitivity/01_extract_sample_buildings.py`
  extracts the sample.

## Licence

Code is under the MIT licence (`LICENSE`). Data produced in this work are under Creative Commons
Attribution 4.0 International (`LICENSE-DATA.md`). The Electricity Authority and MBIE files included here
remain under their publishers' Creative Commons licences, listed in `data/README.md`.

## Citation

Please cite the paper and this repository (https://doi.org/10.5281/zenodo.23487331). Citation details
are in `CITATION.cff`.

## Contact

Ehsan Arab Anvari, Auckland University of Technology.
