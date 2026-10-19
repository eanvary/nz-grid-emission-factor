# New Zealand grid emission factor database: specification

Version: ef-database-v1.0.1 (2026-09-29), a bug-fix release of v1.0. Every statement below
cites the file, override row (`override_id` in `generation_pipeline/fuel_attribution_overrides.csv`)
or external source it rests on.

## 1. What the database contains

The database covers New Zealand's North Island (NI) and South Island (SI), which are joined by
the high-voltage direct current (HVDC) link. Projections follow the Electricity Demand and
Generation Scenarios (EDGS) 2024 of the Ministry of Business, Innovation and Employment (MBIE).

| Part | Period | Resolution | Files | Built by |
|---|---|---|---|---|
| Historical, generation side | Jan 2015 to Aug 2026 (full years 2015-2025) | annual, monthly, daily, hourly; North Island (NI), South Island (SI) | `output/{annual,monthly,daily,hourly}_emission_factor_NI_SI.csv`, `output/monthly_fuel_mix_NI_SI.csv` | `generation_pipeline/build_ef_timeseries.py`, `build_ef_timeseries_daily_hourly.py` |
| Historical, consumption side | as above | annual to hourly | `Consumption_Island/output/*_consumption_EF_NI_SI.csv` | `Consumption_Island/build_*.py` (reallocates the generation-side series across the HVDC link) |
| Projection, primary | 2024-2050, five MBIE EDGS 2024 scenarios | annual and hourly; NI, SI, National | annual `output/edgs/consistent_scope/annual_ef_by_variant.csv` (variant `consistent_scope`, `EF_*_grid`); hourly `output/edgs/edgs_hourly_emission_factor_primary.parquet` | `edgs_pipeline/build_edgs_consistent_scope.py`, `edgs_pipeline/build_edgs_primary_hourly.py` |
| Projection, MBIE-reproducing | as above | annual and hourly | annual variant `combustion_only`; hourly `output/edgs/edgs_hourly_emission_factor*.parquet` | `edgs_pipeline/build_edgs_dispatch.py` and the other `build_edgs_*.py` |

Units are kg CO2e per MWh (`EF_kg_per_MWh`, `EF_*`), which is numerically equal to g/kWh. The
island of each point of connection (POC) comes from the Network Supply Points (NSP) tables of the
Electricity Authority (EA) (`fuel_attribution.poc_island_map`, `EA data/NSP Tables/`).

## 2. Scope decisions

### Emission scope

The emission scope is combustion CO2 at the 2025 gross factors of the Ministry for the
Environment (MfE). These are 54.057909 t CO2/TJ for gas, 91.99 for coal and 69.203964 for diesel
(`MFE_FACTOR_GAS`, `MFE_FACTOR_COAL`, `MFE_FACTOR_DSL`). The source is MfE, Measuring emissions
detailed guide 2025, Table A.2, PDF p180.

Each unit factor is the register heat rate multiplied by the MfE factor
(`generation_pipeline/fuel_attribution.py`, `load_register`). Geothermal fugitive CO2e is
included (section 4), and hydro, wind and solar are zero. Wood (Kinleith) carries CH4 and N2O
only, at 1.52 kg/GJ multiplied by the MBIE wood heat rate, which is an estimate (`KINLEITH_WOOD`).

### Geothermal

Geothermal is included in both the historical series and the projection's consistent-scope
variant, at station intensities (section 4). The national inventory publishes no split between
geothermal electricity and direct use. Check D3-GEO is therefore information only
(`generation_pipeline/validate_ef_database_2015_2025.py`, D3-GEO note).

### Glenbrook

NZ Steel's Glenbrook cogeneration burns off-gas from coal-based ironmaking. Its emissions are
reported under industrial processes and product use (IPPU) category 2.C.1, so it carries zero in
the electricity factor (`GLENBROOK_ZERO`). The sources are MfE, NZ GHG Inventory 1990-2024, Vol 1,
section 4.4.2 p129 and section 3.2.2 p68.

A bound column carries Glenbrook at its gas heat rate multiplied by the MfE gas factor
(567.61 kg/MWh; `fuel_attribution.py`, `glenbrook_bound_ef`). In the projection, 7.63 PJ a year
of Glenbrook-class coal carries zero. MBIE's data isolate this coal only in the Environmental and
Innovation scenarios from 2032. Before 2032 it is assumed to sit inside the 13.59 PJ
(`output/edgs/consistent_scope/NOTES.md`).

### Cogeneration

The metered series contains what Generation_MD in the Electricity Market Information (EMI) data
records. For cogeneration this is grid export only (`validate_ef_database_2015_2025.py`, D2 scope
note). MBIE's electricity emissions include most cogeneration gas. Over 2015-2025 they cover 75%
to 93% of the "Cogeneration" row of the gas data tables, with a mean of 83%. The sources are the
D2 note, `generation_pipeline/MBIE_gas_electricity_PJ_2026Q2.csv` rows 65-66 and
`output/D3_fuel_level_validation.csv`.

Check D2 excludes cogeneration by EMI Tech_Code, so it is scope-mismatched and kept as WARN.

### Generation denominator

The historical denominator is metered injection in EMI Generation_MD plus flagged fills
(section 6). It is a grid-injection basis without rooftop solar or cogeneration self-use
(`build_ef_timeseries.py`).

The projection has two denominators:

- Total generation (`EF_NI`, `EF_National`) equals MBIE total net generation, including all solar
  and cogeneration.
- Grid injection (`EF_NI_grid`, `EF_National_grid`) is MBIE electricity emissions divided by the
  MBIE grid emission factor, multiplied by k. Here k = 0.9741, the mean over 2015-2023 of metered
  generation divided by that implied MBIE grid generation.

The same grid share applies on each island, which is an estimate. The sources are
`edgs_pipeline/build_edgs_consistent_scope.py` and `EDGS_2024_Results.xlsx`, sheets "Greenhouse
gas emissions" and "Emission factors".

## 3. Variants and column names

Historical (`output/*_emission_factor_NI_SI.csv`):

| Column | Meaning | Source |
|---|---|---|
| `EF_kg_per_MWh`, `total_CO2_kg`, `total_gen_MWh` | primary series | `build_ef_timeseries.py` |
| `filled_gen_MWh` | generation from flagged fills | section 6 |
| `CO2_kg_estimated` | CO2 resting on an estimate (Huntly gas portion, wood, proxies, 2025+ geothermal) | `fuel_attribution.py`, `estimated` flag |
| `*_stratford_ccgt`, `*_stratford_peaker` | Stratford at the combined-cycle (SPL0) or peaker (SFD21) record | `STRATFORD_BOUND_CCGT`, `STRATFORD_BOUND_PEAKER` |
| `*_glenbrook_gas` | Glenbrook at gas heat rate instead of zero | `GLENBROOK_ZERO` |

Projection (`output/edgs/consistent_scope/annual_ef_by_variant.csv`, column `variant`):

| Variant | Role | Content | Source |
|---|---|---|---|
| `consistent_scope`, grid basis (`EF_*_grid`) | **primary**: same scope and denominator basis as the historical series | MBIE fuel input x MfE 2025 factors, minus Glenbrook-class coal, plus wood, plus geothermal by plant; grid-injection denominator | `build_edgs_consistent_scope.py` |
| `combustion_only` | **MBIE-reproducing** (check2 5.89%) | MBIE fuel input x MfE 2024 factors (54.0 / 92.6 / 69.4) + wood CH4 and N2O; no geothermal; Glenbrook-class coal included | `edgs_pipeline/build_edgs_dispatch.py`; docstring of `build_edgs_consistent_scope.py` |
| `consistent_new0`, `consistent_new76` | sensitivity | as consistent scope with all new geothermal plant at 0 or 76 g/kWh | same |

The projection file has these columns:

- total-generation denominator: `EF_NI`, `EF_SI`, `EF_National`;
- grid-injection denominator: `EF_NI_grid`, `EF_SI_grid`, `EF_National_grid`, `grid_GWh`,
  `grid_share`, `grid_basis_estimate`;
- other columns: `NI_kt`, `geothermal_kt`, `glenbrook_removed_kt`, `MBIE_kt`.

The unforced check against MBIE totals is in `check2_by_variant.csv`. All thermal and geothermal
plant is in the North Island in the projection register, so `EF_SI` is 0
(`build_edgs_consistent_scope.py` docstring).

### Primary variant, hourly

The hourly primary series, `output/edgs/edgs_hourly_emission_factor_primary.parquet`, has the
columns `scenario`, `island` (NI, SI, National), `datetime_hour`, `emissions_kg`,
`generation_mwh`, `grid_generation_mwh`, `ef_grid_kg_co2e_per_kwh`, `ef_total_kg_co2e_per_kwh`
and `grid_share`.

The annual components in
`output/edgs/consistent_scope/annual_components_consistent_scope.csv` are coal after the
Glenbrook-class deduction, gas, diesel, wood and geothermal. Each component is spread over hours
in proportion to that fuel's hourly generation in `edgs_hourly_generation.parquet` (central
template).

Geothermal per hour therefore equals hourly geothermal generation multiplied by the year's
generation-weighted plant intensity. Glenbrook-class coal is removed in proportion to hourly coal
generation. The denominator is hourly generation multiplied by the year's grid share. Annual sums
reproduce `annual_ef_by_variant.csv` to 4.5e-13 kt (`build_edgs_primary_hourly.py`, check at the
end).

## 4. Factor sources

### Register

The register, read only by `generation_pipeline/fuel_attribution.py`, is EA
`EA data/Dispatched generation plant.csv` (heat rate, fuel, unit, dates). A record is inactive after its
DateDecommissioned (`RULE_DECOMMISSIONED`).

### Unit-level attribution

Huntly E3P and P40 take their own units (`UNIT_E3P`, `UNIT_P40`). The Rotokawa and Te Huka unit
rows (`UNIT_ROTOKAWA`, `UNIT_TEHUKA`) apply only when the New Zealand Geothermal Association
(NZGA) geothermal data are switched off. In the released series, geothermal takes the NZGA
mapping below (`fuel_attribution.py`, `factor_parts`).

### Heat-rate corrections

Heat rates are corrected from the MBIE generation stack reports:

| Plant | Heat rate | Override | Source |
|---|---|---|---|
| Otahuhu B | 7,400 | `HEATRATE_OTA2202` | MBIE 2011 Table 3-1 |
| Stratford peakers | 8,907 | `HEATRATE_SFD21`, `HEATRATE_SFD22` | MBIE 2020 Tables 3-3 and 3-13 |
| Te Rapa | 11,700 | `HEATRATE_TRC1` | MBIE 2020 Tables 3-3 and 3-13 |
| Southdown SWN0, combined cycle | 7,400 | `HEATRATE_SWN0`, `TECH_SWN0` | MBIE 2011 |
| Southdown SWN5 (E105), open cycle | 10,600 | `HEATRATE_SWN5`, `TECH_SWN5` | MBIE 2011 |

### Huntly Units 1-4

Coal and gas are split by Genesis Energy's quarterly "Rankines fuelled by coal" share, uniform
within the quarter (`HUNTLY_COAL_YYYYQn`, 46 quarters). The gas portion is at the Rankine heat
rate multiplied by the MfE gas factor, which is an estimate (`HUNTLY_GAS_PORTION_EF`).

### Geothermal, historical

Station intensities for 2015-2024 come from NZGA: McLean et al. 2024 Table 3 (2015-2022),
Table 2 (2023), and the NZGA slide of 29 July 2025, p6 (2024).

For 2025 the series takes operator-stated intensities for the financial year FY25, July 2024 to
June 2025 (proxy rule step 1, section 5). The values, in g/kWh, are:

- Contact Energy, Green Borrowing Update Report FY25 p4: Tauhara 40.96, Te Mihi 38.94, Wairakei
  20.43, Poihipi 44.09, Te Huka 4.37 and Te Huka 3 1.65.
- Mercury NZ, GHG Emissions Inventory Report FY2025 p19 Figure 3: Kawerau KGL 104.7, Ngā Awa
  Pūrua 51.0, Rotokawa 54.2, Ngā Tamariki 27.3 and Mōkai 18.6. These values are read from the PDF
  vector paths, to about ±1 g/kWh.

Implied station generation is the Table 13 tonnes divided by the stated intensity. It compares
with metered export as follows:

| Station | Implied (GWh) | Metered export (GWh) | Difference |
|---|---|---|---|
| Kawerau KGL | 907.3 | 908.4 | -0.1% |
| Ngā Awa Pūrua | 1,225.5 | 1,195.0 | +2.6% |
| Rotokawa | 240.6 | 162.7 | +47.9% |
| Ngā Tamariki | 839.9 | 688.3 | +22.1% |
| Mōkai | 1,025.0 | 750.7 | +36.5% |

Mercury itself reports 688 GWh for Ngā Tamariki in its FY2025 Allocation of Proceeds Report, and
the gap is unexplained. Other stations hold 2024, and every value is listed in
`generation_pipeline/geothermal_intensity_nzga.csv`.

Generators map to stations through 18 `GEO_MAP_*` rows, which include the Onepu composite for
norskeskog (TOPP1 and GDL weighted by NZGA 2023 output). They also include dated rows for
`kawerau_(topp2)`: Te Ahi O Maui (TAOM) to 2 December 2025, and the TOPP1 proxy from 3 December
2025.

### Geothermal, projection

The projection uses `edgs_pipeline/geothermal_projection_intensity.csv`, with one row per plant
and its rule and source. Existing plant takes the NZGA value for calendar year 2024 (CY2024).
From 2025 a plant takes its FY25 stated value only where the operator does not identify FY25 as
affected by outage, commissioning or ramp-up (clause (b)). This applies to Kawerau KGL 104.7,
Mōkai 18.6 and Poihipi 44.09 (columns `measured_year`, `g_per_kwh_measured`).

CY2024 is kept for these plants:

- Ngā Awa Pūrua and Rotokawa: planned outages (Mercury Interim Report 2025 p5).
- Te Mihi, Wairakei and Te Huka: turnarounds and an electrical outage (Contact FY25 and HY25
  results presentations; Integrated Report 2025 p56).
- Tauhara, at 48: final commissioning and ramp-up in 1H25 (Contact FY24 results presentation
  slide 32; HY25 slides 7 and 29).

Te Huka 3 follows Te Huka (step 3), because its FY25 value of 1.65 is from a commissioning year.

Ngā Tamariki and its expansion take 39 in 2024 and the stated 27.3 in 2025. From 2026 they follow
Mercury's station trajectory of 1.9 t/h, falling to 1.0 t/h by 2051 (NZGA CO2 group presentation,
July 2024, slide 7). The trajectory is converted on Mercury's reported-generation basis under
clause (a). That basis is the operator's own figure of 1,120 GWh a year (Mercury NZX release,
21 January 2026). The result is 14.86 g/kWh in 2026, falling to 7.82 in 2051, and is an estimate.

One inconsistency is flagged: the 2025 value (27.3) is on Mercury's intensity basis, which
implies 839.9 GWh. Values from 2026 onward are on Mercury's reported-generation basis (688 GWh in
FY2025). The step from 2025 to 2026 therefore mixes two Mercury bases. Values per plant and year
are in `output/edgs/consistent_scope/geothermal_intensity_by_plant_year.csv`.

## 5. Proxy rule (geothermal)

The proxy rule applies these steps in order (`RULE_GEO_PROXY_ORDER`; root `README.md`):

1. A source-specific figure. A publisher's stated intensity is a step-1 source and outranks any
   derived value. Where two source-specific figures exist, the most recent measured period wins.
2. The same station's nearest published year.
3. The nearest station on the same field, through a `GEO_MAP_*` row. In the projection this is a
   `follows` row, which takes the reference station's whole time path.
4. The NZGA MW-weighted fleet average.

Steps 2 to 4 are flagged. Two clauses limit the rule:

- Clause (a): never derive an intensity from metered export; derive one only where no stated
  intensity exists, and only with the operator's own generation figure.
- Clause (b): a period that the operator identifies as outage-affected, or as commissioning or
  ramp-up, is not carried forward into the projection.

Examples:

- 2025 takes the Contact and Mercury FY25 stated values (step 1). Mercury values derived from
  metered export are withdrawn under clause (a).
- Clause (b) applies to the plants listed in section 4.
- norskeskog 2015-2016 takes TOPP1's 2017 value (step 2, `geothermal_intensity_nzga.csv`).
- TOPP2 follows TOPP1 (step 3).
- New fields take 53 g/kWh (step 4).

## 6. Fill methods

Every fill is flagged per trading period in `output/filled_generation_log.csv` and summarised
per fill and month, with ratios and cross-checks, in
`output/filled_generation_summary.csv`.

| Fill | Period | GWh | Basis | Override |
|---|---|---|---|---|
| Huntly Units 1-4 | Sep 2020 | 224.07 | Genesis Q1 FY21 Rankine output 585 GWh less metered July-August, shaped by their profile | `HUNTLY_FILL_2020_09` |
| Huntly E3P and P40 | Sep 2020 | 247.40 and 6.05 | Grid_import HLY2201 x Generation_MD/Grid_import ratio (Aug and Oct 2020) less the Rankine fill, split by July-August shares; Genesis cross-check +11.6% | `GRIDIMPORT_FILL_HLY2201_2020_09`, `FILLCHECK_HLY2201_2020_09` |
| norskeskog (KAW0112) | 2015-2019 | 989.02 | Grid_import x ratio 1.000 (Jan 2020) | `GRIDIMPORT_FILL_KAW0112_2015_2019` |
| Matahina (MAT1101) | Oct 2021 to Dec 2025 | 1,342.43 | Grid_import generator stream (Generation_Type GG), measured: equals Generation_MD Matahina in every month Jan 2015 to Sep 2021 | `GRIDIMPORT_FILL_MAT1101_2021_10_2025_12` |

For Matahina, the measured stream is used in place of fills based on Manawa fiscal-year totals and
a long-term average.

## 7. Validation

The validation suite is `generation_pipeline/validate_ef_database_2015_2025.py`, with results in
`output/DATA_QUALITY_ASSESSMENT_RESULTS.{csv,txt}`. MBIE is a validation target only, never an
input (same script, D-check notes). Status at v1.0 was 37 PASS, 2 WARN, 0 FAIL and 4 INFO, out of
43 checks.

The two WARN results are explained and are not defects:

- D2 compares a cogeneration-excluded metered series with MBIE totals that include most
  cogeneration gas (section 2).
- E6 lists 45 zero-output POC-months between generating months. One is covered by a flagged
  fill, and the rest are real outages or reporting under another POC (`output/completeness_flags.csv`).

The four INFO checks are H7b and H7c (resolution dependence of the island split, by design),
D3-GEO (no scope-matched target) and D3-GAS-emissions (cogeneration scope).

## 7a. Uncertainty (gas and geothermal factors)

The script `docs/validation/build_fleet_uncertainty.py` writes `fleet_uncertainty_by_fuel.csv`,
and five propagation scripts read its `rel_sigma_adopted`:

- `run_ipcc_uncertainty_fleet_adjusted.py`
- `run_ipcc_uncertainty_full_coverage.py`
- `run_ipcc_uncertainty_montecarlo.py`
- `test_geothermal_sigma_sensitivity.py`
- `test_montecarlo_trial_convergence.py`

### Gas

The gas relative sigma is the per-unit factor uncertainty, `sqrt(carbon^2 + heatrate^2)`. The
carbon term comes from the Intergovernmental Panel on Climate Change (IPCC) (2006), Vol 2 Ch 2
Table 2.2, natural gas. The default there is 56,100 kg/TJ (54,300-58,300), a relative half-width
of 0.0357.

The heat-rate term is the root mean square (RMS) of the D3 gas-fuel annual residuals over
2015-2025, which is 0.0194 (`output/D3_fuel_level_validation.csv`, check GAS-PJ). The combined
result is 0.0406.

As a cross-check, register heat rates were compared with MBIE generation-stack heat rates for gas
plants of the same type, after the `HEATRATE_*` corrections. The RMS is 1.42% over nine plants
and 2.14% over the four uncorrected ones (Taranaki CC +4.05%, Huntly 5 -1.35%). The sources are
MBIE 2011 Table 3-1, MBIE 2020 Tables 3-3 and 3-13, and `docs/validation/gas_heat_rate_audit.csv`.

The generation-weighted spread of the unit factors (0.0674 pooled, 0.1615 unit-level) is stored
as `rel_sigma_fleet` for the record and is not adopted. With unit-level factors it double-counts
known heterogeneity. Coal, diesel and wood keep the IPCC Table 2.2 ranges.

### Geothermal

From release v1.0.1 (2026-09-29), geothermal uncertainty is set by proxy-rule step, and each
term is propagated as an independent fuel (`docs/validation/build_geo_uncertainty_inputs.py`).

#### Step 1

Step 1 (`GEO`, source-specific intensity) uses 7.07% = `sqrt(5.0^2 + 5.0^2)`. The source is the
National Inventory Report (NIR) 2026, Vol 1, section 3.2.3. Table 3.2.3 there is titled
"Uncertainty for New Zealand's energy sector emission estimates for 2024" (printed pp72-73). Its
row "Fugitive - Other forms of energy production (geothermal)" gives activity data ±5.0% and
emission factor ±5.0% for CO2, and the CH4 row gives the same.

#### Step 2

Step 2 (`GEO_S2_<station>`) is the station's nearest published year, including 2025 values held
from 2024 and every 2026 month.

Its sigma is `sqrt(7.07%^2 + s_station^2)`, where s_station is the RMS of the station's year-on-year relative changes in the NZGA series
2015-2024. The series uses published values, and pairs with a zero previous value are skipped.
Stations with fewer than 3 published years, or none, take the pooled value over all stations,
21.91%. These stations are Tauhara, Ngāwhā OEC4 and Te Huka 3.

Values of s_station (`docs/validation/geo_step2_station_variation.csv`):

| Station | s_station |
|---|---|
| Te Mihi | 6.93% |
| Ngā Awa Pūrua | 9.81% |
| Wairakei | 11.72% |
| Ohaaki | 12.53% |
| Ngā Tamariki | 13.63% |
| Kawerau KGL | 14.47% |
| TOPP1 | 15.12% |
| Rotokawa | 16.05% |
| Mōkai | 16.90% |
| TAOM | 17.70% |
| GDL | 20.06% |
| Te Huka | 35.89% |
| Poihipi | 38.94% |
| Ngāwhā OEC1-3 | 39.36% |

The RMS counts step changes from reinjection as variation, for example Te Huka 24 to 4 and Ngāwhā
to 0.

#### Steps 3 and 4

Steps 3 and 4 (`GEO_PROXY`) cover the same-field or composite proxy and the NZGA fleet average.
They take the MW-weighted between-station spread of McLean and Richardson (2019), 93.97%.

#### Output files and step shares

The outputs are `geo_uncertainty_sigma.csv` (one row per term), `monthly_fuel_mix_uncertainty.csv`
and `hourly_fuel_mix_uncertainty.csv`. The hourly split uses each month's shares, which is an
approximation. Each generator-month is classified by step from the attribution rule and the basis
column of `generation_pipeline/geothermal_intensity_nzga.csv`.

Share of North Island geothermal CO2 by step:

- 2015-2024: step 1 97% to 98%, steps 3-4 2% to 3%.
- 2025: step 1 44%, step 2 53%, steps 3-4 3%.
- 2026: step 2 91.5%, steps 3-4 8.5%.

### Resulting bands

Monte Carlo gives the North Island mean 95% bands below, as % of the point value
(`run_ipcc_uncertainty_montecarlo.py`). Over all years, 2015 to August 2026, the bands are hourly
12.84%, monthly 12.05% and annual 11.23%. With the fleet-wide geothermal spread in place of the
step terms, they would be 72.01%, 63.15% and 54.04%.

For 2015-2025 alone the bands are hourly 12.48%, monthly 11.82% and annual 10.96%, with 10.1% to
12.2% by year. The annual band is 10.2% for 2025 and 14.1% for partial 2026. The sources are
`docs/validation/ipcc_uncertainty_by_island_{hour,month,year}_montecarlo.csv`.

Approach 1 (analytic) gives 12.9% for the hourly band, against Approach 2's 12.8%. No hour has a
negative lower bound (`docs/validation/geothermal_sigma_sensitivity.csv`, row "as released").
Approach 1 still formally fails the IPCC coefficient-of-variation test (section 8), so Approach 2
is the reported method.

## 8. Known limitations

- The Huntly gas portion and the 2015 Q1-Q2 coal share rest on Genesis quarterly figures and the
  Rankine heat rate, and both are estimates (`HUNTLY_GAS_PORTION_EF`, `HUNTLY_COAL_YYYYQn`).
- Stratford stays pooled under one generator code, with bounds in the Stratford columns
  (`STRATFORD_BOUND_*`).
- Geothermal intensities for 2025 are operator-stated FY25 values, and Mercury's are read from a
  chart to about ±1 g/kWh.
- Mercury's stated intensities imply station generation 22% to 48% above metered export for Ngā
  Tamariki, Mōkai and Rotokawa. Ngā Tamariki is also 22% above Mercury's own reported 688 GWh.
  Mercury does not state its denominator.
- Stations without FY25 figures hold 2024, and 2026 months take the nearest published year
  (`fuel_attribution.py`, `_nzga_nearest`). FY25 is July to June, not the calendar year.
- Gas factor uncertainty is an estimate built from two sourced terms (section 7a). It is a Tier-1
  carbon range plus an empirical heat-rate term, not a plant-by-plant measurement.
- Geothermal step 1 uses the NIR category-level 7.07% for every station, because no
  station-specific measurement uncertainty is published.
- Geothermal step 2 counts reinjection step changes as year-to-year variation in s_station. The
  cases are Te Huka, 24 to 4 g/kWh in 2024, and Ngāwhā OEC1-3, to 0 in 2023. Their step-2 sigmas
  (Te Huka 36.58%, Ngāwhā OEC1-3 39.99%) are therefore conservative
  (`docs/validation/geo_step2_station_variation.csv`).
- Approach 1 formally fails the IPCC coefficient-of-variation test (30% limit) because of the
  steps 3-4 geothermal term (93.97%). It still agrees with Approach 2: 12.9% against 12.8% for the
  NI mean hourly band, with no negative lower bound in any hour (`geothermal_sigma_sensitivity.csv`).
  Monte Carlo (Approach 2) is therefore the reported method.
- Data files over 100 MB, such as `output/edgs/edgs_hourly_generation*.parquet`,
  `output/edgs/edgs_hourly_emission_factor_primary.parquet` and
  `output/zone_historical/zone_ef_TP_2015_2025.parquet`, cannot be pushed to GitHub, which has a
  100 MB per-file limit. The last is 242 MB and comes from the
  separate zone-database commit 07c595e. Sizes of the database files are in `DATA_MANIFEST.csv`.
  Publication will need a data deposit, for example a repository that mints a digital object
  identifier (DOI), with `DATA_MANIFEST.csv` (path, size, SHA-256) as the integrity check.
- The EDGS hourly shape templates (2017, 2021, 2023, 2024) are built from raw Generation_MD
  without the fills. The fills are 2.7% of NI geothermal in 2017 (norskeskog). They are 1.1%,
  4.8% and 3.9% of NI hydro in 2021, 2023 and 2024 (Matahina), and at most 6.0% of NI hydro in
  any month. As a share of national generation they are 0.15% to 0.88%. The sources are
  `edgs_pipeline/build_edgs_hourly_shape.py`, `output/filled_generation_summary.csv` and
  `output/monthly_fuel_mix_NI_SI.csv`. The shapes are normalised per island and fuel, and annual
  volumes come from MBIE.
- KAW0111 (`kawerau`) is Te Ahi O Maui net of about 11 MW of local load. KAW0112 (`norskeskog`)
  may include Oji wood cogeneration from April 2023, which is unconfirmed (`GEO_MAP_kawerau`,
  `GEO_MAP_norskeskog`).
- The E3P and P40 September 2020 fill is 11.6% above the Genesis quarterly gas figure once Rankine
  gas is removed (`FILLCHECK_HLY2201_2020_09`).
- Roaring Meg is not measurable in Generation_MD or Grid_import (CML0331) and is absent.
- Real zero-output months remain (completeness check E6, `output/completeness_flags.csv`).
- Cogeneration is counted as export only (section 2).
- The consumption side inherits every generation-side limitation.
- In the projection, MBIE's accounting boundary changes at 2023/2024, and projected totals equal
  combustion only. The consistent-scope variant therefore does not reproduce MBIE totals, by
  construction (`output/edgs/consistent_scope/NOTES.md`).
- The projection's grid denominator uses one grid share for both islands and MBIE's factor to four
  decimals. Glenbrook-class coal is assumed to sit inside MBIE's coal before 2032.
- TIMES-NZ is used as a comparison on the combustion side only
  (`reference_data/times_nz_3/README.md`).
