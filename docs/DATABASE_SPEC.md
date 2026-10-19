# New Zealand grid emission factor database: specification

Version: ef-database-v1.0.1 (2026-09-29), a bug-fix release of v1.0. Every statement
below cites the file, override row (`override_id` in
`generation_pipeline/fuel_attribution_overrides.csv`) or external source it rests on.

## 1. What the database contains

| Part | Period | Resolution | Files | Built by |
|---|---|---|---|---|
| Historical, generation side | Jan 2015 to Aug 2026 (full years 2015-2025) | annual, monthly, daily, hourly; North Island (NI), South Island (SI) | `output/{annual,monthly,daily,hourly}_emission_factor_NI_SI.csv`, `output/monthly_fuel_mix_NI_SI.csv` | `generation_pipeline/build_ef_timeseries.py`, `build_ef_timeseries_daily_hourly.py` |
| Historical, consumption side | as above | annual to hourly | `Consumption_Island/output/*_consumption_EF_NI_SI.csv` | `Consumption_Island/build_*.py` (reallocates the generation-side series across the HVDC link) |
| Projection, primary | 2024-2050, five MBIE EDGS 2024 scenarios | annual and hourly; NI, SI, National | annual `output/edgs/consistent_scope/annual_ef_by_variant.csv` (variant `consistent_scope`, `EF_*_grid`); hourly `output/edgs/edgs_hourly_emission_factor_primary.parquet` | `edgs_pipeline/build_edgs_consistent_scope.py`, `edgs_pipeline/build_edgs_primary_hourly.py` |
| Projection, MBIE-reproducing | as above | annual and hourly | annual variant `combustion_only`; hourly `output/edgs/edgs_hourly_emission_factor*.parquet` | `edgs_pipeline/build_edgs_dispatch.py` and the other `build_edgs_*.py` |

Units: kg CO2e per MWh (`EF_kg_per_MWh`, `EF_*`), numerically equal to g/kWh. Island of each point
of connection (POC) from the EA Network Supply Points tables (`fuel_attribution.poc_island_map`,
`EA data/NSP Tables/`).

## 2. Scope decisions

**Emission scope.** Combustion CO2 at MfE 2025 gross factors: gas 54.057909, coal 91.99, diesel
69.203964 t CO2/TJ (MfE, Measuring emissions detailed guide 2025, Table A.2, PDF p180;
`MFE_FACTOR_GAS`, `MFE_FACTOR_COAL`, `MFE_FACTOR_DSL`). Unit factor = register heat rate x MfE
factor (`generation_pipeline/fuel_attribution.py`, `load_register`). Geothermal fugitive CO2e is
included (section 4). Wood (Kinleith) carries CH4 and N2O only, 1.52 kg/GJ x MBIE wood heat rate,
an estimate (`KINLEITH_WOOD`). Hydro, wind and solar are zero.

**Geothermal.** Included in both the historical series and the projection's consistent-scope
variant, at station intensities (section 4). The national inventory publishes no split between
geothermal electricity and direct use, so check D3-GEO is information only
(`generation_pipeline/validate_ef_database_2015_2025.py`, D3-GEO note).

**Glenbrook.** NZ Steel's Glenbrook cogeneration burns off-gas from coal-based ironmaking; its
emissions are reported under IPPU 2.C.1, so it carries zero in the electricity factor
(`GLENBROOK_ZERO`; MfE, NZ GHG Inventory 1990-2024, Vol 1, section 4.4.2 p129 and section 3.2.2
p68). A bound column carries it at its gas heat rate x MfE gas factor (567.61 kg/MWh;
`fuel_attribution.py`, `glenbrook_bound_ef`). In the projection, 7.63 PJ of Glenbrook-class coal
a year carries zero; this is isolated in MBIE's data only in Environmental and Innovation from
2032, and is assumed to sit inside the 13.59 PJ before 2032 (`output/edgs/consistent_scope/NOTES.md`).

**Cogeneration.** The metered series contains what EMI Generation_MD records, which for
cogeneration is grid export only (`validate_ef_database_2015_2025.py`, D2 scope note). MBIE's
electricity emissions include most cogeneration gas: 75% to 93% of the gas data tables'
"Cogeneration" row, mean 83%, 2015-2025 (D2 note; `generation_pipeline/MBIE_gas_electricity_PJ_2026Q2.csv`
rows 65-66; `output/D3_fuel_level_validation.csv`). D2 (cogeneration excluded by EMI Tech_Code)
is therefore scope-mismatched and kept as WARN.

**Generation denominator.** Historical: metered injection in EMI Generation_MD plus flagged fills
(section 5), i.e. a grid-injection basis without rooftop solar or cogeneration self-use
(`build_ef_timeseries.py`). Projection: two denominators, total generation (`EF_NI`,
`EF_National`: equals MBIE total net generation, all solar and cogeneration) and grid injection
(`EF_NI_grid`, `EF_National_grid`): MBIE electricity emissions / MBIE grid emission factor x k,
k = 0.9741 = mean 2015-2023 of metered generation / that implied MBIE grid generation; same grid
share on each island, an estimate (`edgs_pipeline/build_edgs_consistent_scope.py`;
`EDGS_2024_Results.xlsx` sheets "Greenhouse gas emissions" and "Emission factors").

## 3. Variants and column names

Historical (`output/*_emission_factor_NI_SI.csv`):

| Column | Meaning | Source |
|---|---|---|
| `EF_kg_per_MWh`, `total_CO2_kg`, `total_gen_MWh` | primary series | `build_ef_timeseries.py` |
| `filled_gen_MWh` | generation from flagged fills | section 5 |
| `CO2_kg_estimated` | CO2 resting on an estimate (Huntly gas portion, wood, proxies, 2025+ geothermal) | `fuel_attribution.py`, `estimated` flag |
| `*_stratford_ccgt`, `*_stratford_peaker` | Stratford at the combined-cycle (SPL0) or peaker (SFD21) record | `STRATFORD_BOUND_CCGT`, `STRATFORD_BOUND_PEAKER` |
| `*_glenbrook_gas` | Glenbrook at gas heat rate instead of zero | `GLENBROOK_ZERO` |

Projection (`output/edgs/consistent_scope/annual_ef_by_variant.csv`, column `variant`):

| Variant | Role | Content | Source |
|---|---|---|---|
| `consistent_scope`, grid basis (`EF_*_grid`) | **primary**: same scope and denominator basis as the historical series | MBIE fuel input x MfE 2025 factors, minus Glenbrook-class coal, plus wood, plus geothermal by plant; grid-injection denominator | `build_edgs_consistent_scope.py` |
| `combustion_only` | **MBIE-reproducing** (check2 5.89%) | MBIE fuel input x MfE 2024 factors (54.0 / 92.6 / 69.4) + wood CH4 and N2O; no geothermal; Glenbrook-class coal included | `edgs_pipeline/build_edgs_dispatch.py`; docstring of `build_edgs_consistent_scope.py` |
| `consistent_new0`, `consistent_new76` | as consistent scope with all new geothermal plant at 0 or 76 g/kWh | same |

Columns: `EF_NI`, `EF_SI`, `EF_National` (total-generation denominator); `EF_NI_grid`, `EF_SI_grid`,
`EF_National_grid`, `grid_GWh`, `grid_share`, `grid_basis_estimate` (grid-injection denominator);
`NI_kt`, `geothermal_kt`, `glenbrook_removed_kt`, `MBIE_kt`. Check against MBIE totals, unforced:
`check2_by_variant.csv`. All thermal and geothermal plant is North Island in the projection
register, so `EF_SI` is 0 (`build_edgs_consistent_scope.py` docstring).

Primary variant, hourly (`output/edgs/edgs_hourly_emission_factor_primary.parquet`; columns
`scenario`, `island` (NI, SI, National), `datetime_hour`, `emissions_kg`, `generation_mwh`,
`grid_generation_mwh`, `ef_grid_kg_co2e_per_kwh`, `ef_total_kg_co2e_per_kwh`, `grid_share`).
Each annual component (`output/edgs/consistent_scope/annual_components_consistent_scope.csv`:
coal after the Glenbrook-class deduction, gas, diesel, wood, geothermal) is spread over hours in
proportion to that fuel's hourly generation in `edgs_hourly_generation.parquet` (central
template); geothermal per hour therefore equals hourly geothermal generation x the year's
generation-weighted plant intensity, and Glenbrook-class coal is removed in proportion to hourly
coal generation. Denominator: hourly generation x the year's grid share. Annual sums reproduce
`annual_ef_by_variant.csv` to 4.5e-13 kt (`build_edgs_primary_hourly.py`, check at the end).

## 4. Factor sources

- **Register.** EA `EA data/Dispatched generation plant.csv` (heat rate, fuel, unit, dates), read
  only by `generation_pipeline/fuel_attribution.py`. A record is inactive after its
  DateDecommissioned (`RULE_DECOMMISSIONED`).
- **Unit-level attribution.** Huntly E3P and P40 take their own units (`UNIT_E3P`, `UNIT_P40`).
  The Rotokawa and Te Huka unit rows (`UNIT_ROTOKAWA`, `UNIT_TEHUKA`) apply only when NZGA
  geothermal is switched off; in the released series geothermal takes the NZGA mapping below
  (`fuel_attribution.py`, `factor_parts`).
- **Heat-rate corrections** (MBIE generation stack reports): Otahuhu B 7,400 (`HEATRATE_OTA2202`,
  MBIE 2011 Table 3-1); Stratford peakers 8,907 (`HEATRATE_SFD21`, `HEATRATE_SFD22`) and Te Rapa
  11,700 (`HEATRATE_TRC1`), MBIE 2020 Tables 3-3 and 3-13; Southdown SWN0 combined cycle 7,400 and
  SWN5 (E105) open cycle 10,600 (`HEATRATE_SWN0`, `HEATRATE_SWN5`, `TECH_SWN0`, `TECH_SWN5`, MBIE 2011).
- **Huntly Units 1-4.** Coal and gas by Genesis Energy's quarterly "Rankines fuelled by coal"
  share, uniform within the quarter (`HUNTLY_COAL_YYYYQn`, 46 quarters); gas portion at the Rankine
  heat rate x MfE gas factor, an estimate (`HUNTLY_GAS_PORTION_EF`).
- **Geothermal.** NZGA station intensities: McLean et al. 2024 Table 3 (2015-2022), Table 2 (2023),
  NZGA 29 July 2025 slide p6 (2024). 2025 takes operator-stated FY25 intensities (Jul 2024-Jun
  2025; proxy rule step 1, section 5): Contact Energy, Green Borrowing Update Report FY25 p4, for
  Tauhara 40.96, Te Mihi 38.94, Wairakei 20.43, Poihipi 44.09, Te Huka 4.37 and Te Huka 3 1.65;
  Mercury NZ, GHG Emissions Inventory Report FY2025 p19 Figure 3 (read from the PDF vector paths,
  about +/-1 g/kWh), for Kawerau KGL 104.7, Ngā Awa Pūrua 51.0, Rotokawa 54.2, Ngā Tamariki 27.3
  and Mōkai 18.6. Implied station generation (Table 13 tonnes / stated intensity) against metered
  export: Kawerau 907.3 vs 908.4 GWh (-0.1%), Ngā Awa Pūrua 1,225.5 vs 1,195.0 (+2.6%), Rotokawa
  240.6 vs 162.7 (+47.9%), Ngā Tamariki 839.9 vs 688.3 (+22.1%; Mercury itself reports 688 GWh,
  FY2025 Allocation of Proceeds Report: an unexplained gap), Mōkai 1,025.0 vs 750.7 (+36.5%).
  Other stations hold 2024. Per value: `generation_pipeline/geothermal_intensity_nzga.csv`.
  Generator-to-station mapping: `GEO_MAP_*` rows (18), including the Onepu composite for
  norskeskog (TOPP1 and GDL weighted by NZGA 2023 output) and dated rows for `kawerau_(topp2)`
  (TAOM to 2 December 2025, TOPP1 proxy from 3 December 2025).
- **Projection geothermal.** `edgs_pipeline/geothermal_projection_intensity.csv` (one row per plant,
  with rule and source): existing plant at NZGA CY2024, and from 2025 at an FY25 stated value only
  where the operator does not identify FY25 as outage, commissioning or ramp-up affected (clause
  (b)): Kawerau 104.7, Mōkai 18.6 and Poihipi 44.09 (columns `measured_year`,
  `g_per_kwh_measured`). CY2024 is kept for Ngā Awa Pūrua and Rotokawa (planned outages, Mercury
  Interim Report 2025 p5), Te Mihi, Wairakei and Te Huka (turnarounds and an electrical outage,
  Contact FY25 and HY25 results presentations, Integrated Report 2025 p56) and Tauhara 48 (final
  commissioning and ramp-up in 1H25, Contact FY24 results presentation slide 32, HY25 slides 7 and
  29); Te Huka Unit 3 follows Te Huka (step 3), its FY25 1.65 being a commissioning year.
  Ngātamariki (and its expansion): 39 (2024), 27.3 (2025, stated), then Mercury's station
  trajectory, 1.9 t/h from 2026 falling to 1.0 t/h by 2051 (NZGA CO2 group presentation July 2024
  slide 7), converted on Mercury's reported-generation basis under clause (a), the operator's own
  figure of 1,120 GWh a year (Mercury NZX release 21 January 2026): 14.86 g/kWh (2026) to 7.82
  (2051), an estimate. FLAG: 2025 (27.3) is on Mercury's intensity basis (implied 839.9 GWh) and
  2026 onward on its reported-generation basis (688 GWh in FY2025), so the step from 2025 to 2026
  mixes two Mercury bases. Per plant and year:
  `output/edgs/consistent_scope/geothermal_intensity_by_plant_year.csv`.

## 5. Proxy rule (geothermal)

In order (`RULE_GEO_PROXY_ORDER`; root `README.md`): (1) a source-specific figure; a
publisher's stated intensity is a step-1 source and outranks any derived value, and where two
source-specific figures exist the most recent measured period wins; (2) the same station's
nearest published year; (3) the nearest station on the same field (a `GEO_MAP_*` row; in the
projection a `follows` row that takes the reference station's whole time path); (4) the NZGA
MW-weighted fleet average. Clause (a): never derive an intensity from metered export; derive only
where no stated intensity exists, and only with the operator's own generation figure. Clause (b):
a period the operator identifies as outage-affected, or as commissioning or ramp-up, is not
carried forward into the projection. Steps 2 to 4 are flagged. Examples: 2025 at the Contact and
Mercury FY25 stated values (step 1; the earlier Mercury values derived from metered export are
withdrawn under clause (a)); clause (b) as listed in section 4; norskeskog 2015-2016 at TOPP1's
2017 value (step 2, `geothermal_intensity_nzga.csv`); TOPP2 follows TOPP1 (step 3); new fields at
53 g/kWh (step 4).

## 6. Fill methods

All fills are flagged per trading period in `output/filled_generation_log.csv` and summarised per
fill and month, with ratios and cross-checks, in `output/filled_generation_summary.csv`.

| Fill | Period | GWh | Basis | Override |
|---|---|---|---|---|
| Huntly Units 1-4 | Sep 2020 | 224.07 | Genesis Q1 FY21 Rankine output 585 GWh less metered July-August, shaped by their profile | `HUNTLY_FILL_2020_09` |
| Huntly E3P and P40 | Sep 2020 | 247.40 and 6.05 | Grid_import HLY2201 x Generation_MD/Grid_import ratio (Aug and Oct 2020) less the Rankine fill, split by July-August shares; Genesis cross-check +11.6% | `GRIDIMPORT_FILL_HLY2201_2020_09`, `FILLCHECK_HLY2201_2020_09` |
| norskeskog (KAW0112) | 2015-2019 | 989.02 | Grid_import x ratio 1.000 (Jan 2020) | `GRIDIMPORT_FILL_KAW0112_2015_2019` |
| Matahina (MAT1101) | Oct 2021 to Dec 2025 | 1,342.43 | Grid_import generator stream (Generation_Type GG), measured: equals Generation_MD Matahina in every month Jan 2015 to Sep 2021 | `GRIDIMPORT_FILL_MAT1101_2021_10_2025_12` |

The measured stream replaced earlier Matahina fills based on Manawa fiscal-year totals and a
long-term average.

## 7. Validation

Suite: `generation_pipeline/validate_ef_database_2015_2025.py`, results in
`output/DATA_QUALITY_ASSESSMENT_RESULTS.{csv,txt}`. MBIE is a validation target only, never an
input (same script, D-check notes). Status at v1.0: 37 PASS, 2 WARN, 0 FAIL, 4 INFO (43 checks).
The two WARNs are explained, not defects: D2 compares a cogeneration-excluded metered series
with MBIE totals that include most cogeneration gas (section 2); E6 lists 45 zero-output
POC-months between generating months, one covered by a flagged fill and the rest real outages
or reporting under another POC (`output/completeness_flags.csv`). The four INFO checks are
H7b and H7c (resolution dependence of the island split, by design), D3-GEO (no scope-matched
target) and D3-GAS-emissions (cogeneration scope).

## 7a. Uncertainty (gas and geothermal factors)

`docs/validation/build_fleet_uncertainty.py` writes `fleet_uncertainty_by_fuel.csv`; the five
propagation scripts (`run_ipcc_uncertainty_fleet_adjusted.py`, `run_ipcc_uncertainty_full_coverage.py`,
`run_ipcc_uncertainty_montecarlo.py`, `test_geothermal_sigma_sensitivity.py`,
`test_montecarlo_trial_convergence.py`) read its `rel_sigma_adopted`.
Gas: relative sigma = sqrt(carbon^2 + heatrate^2), per-unit factor uncertainty. carbon = IPCC (2006)
Vol 2 Ch 2 Table 2.2 natural gas, default 56,100 kg/TJ (54,300-58,300), relative half-width 0.0357;
heatrate = RMS of the D3 gas-fuel annual residuals 2015-2025 (`output/D3_fuel_level_validation.csv`,
check GAS-PJ), 0.0194; result 0.0406. Cross-check: register vs MBIE generation-stack heat rates for
gas plants of the same type after the `HEATRATE_*` corrections, RMS 1.42% over nine plants and
2.14% over the four uncorrected ones (Taranaki CC +4.05%, Huntly 5 -1.35%; MBIE 2011 Table 3-1,
MBIE 2020 Tables 3-3 and 3-13; `docs/validation/gas_heat_rate_audit.csv`). The previous gas sigma,
the generation-weighted spread of the unit factors (0.0674 pooled, 0.1615 unit-level), is kept as
`rel_sigma_fleet` for the record: with unit-level factors it double-counts known heterogeneity.
Coal, diesel and wood keep the IPCC Table 2.2 ranges.

Geothermal (since 2026-09-29, `docs/validation/build_geo_uncertainty_inputs.py`): uncertainty by
proxy-rule step, each term propagated as an independent fuel.
- Step 1 (`GEO`, source-specific intensity): 7.07% = sqrt(5.0^2 + 5.0^2), from NIR 2026 Vol 1
  section 3.2.3, Table 3.2.3 "Uncertainty for New Zealand's energy sector emission estimates for
  2024" (printed pp72-73): "Fugitive - Other forms of energy production (geothermal)", activity
  data +/-5.0% and emission factor +/-5.0% (CO2; the CH4 row gives the same).
- Step 2 (`GEO_S2_<station>`, the station's nearest published year, including 2025 values held
  from 2024 and every 2026 month): sqrt(7.07%^2 + s_station^2), where s_station is the RMS of the
  station's year-on-year relative changes in the NZGA series 2015-2024 (published values; pairs
  with a zero previous value skipped). Stations with fewer than 3 published years, or none, take
  the pooled value over all stations, 21.91% (Tauhara, Ngāwhā OEC4, Te Huka 3). s_station: Te Mihi
  6.93%, Ngā Awa Pūrua 9.81%, Wairakei 11.72%, Ohaaki 12.53%, Ngā Tamariki 13.63%, Kawerau KGL
  14.47%, TOPP1 15.12%, Rotokawa 16.05%, Mōkai 16.90%, TAOM 17.70%, GDL 20.06%, Te Huka 35.89%,
  Poihipi 38.94%, Ngāwhā OEC1-3 39.36% (`docs/validation/geo_step2_station_variation.csv`). The
  RMS counts step changes from reinjection (Te Huka 24 to 4, Ngāwhā to 0) as variation.
- Steps 3 and 4 (`GEO_PROXY`: same-field or composite proxy; NZGA fleet average): the
  MW-weighted between-station spread of McLean and Richardson (2019), 93.97%.
Files: `geo_uncertainty_sigma.csv` (one row per term), `monthly_fuel_mix_uncertainty.csv`,
`hourly_fuel_mix_uncertainty.csv` (the hourly split uses each month's shares, an approximation).
Step classification is per generator-month, from the attribution rule and the basis column of
`generation_pipeline/geothermal_intensity_nzga.csv`. Share of North Island geothermal CO2 by
step: 2015-2024 step 1 97% to 98%, steps 3-4 2% to 3%; 2025 step 1 44%, step 2 53%, steps 3-4 3%;
2026 step 2 91.5%, steps 3-4 8.5%.

Resulting North Island mean 95% bands, Monte Carlo (`run_ipcc_uncertainty_montecarlo.py`, % of the
point value, all years 2015 to August 2026): hourly 12.84%, monthly 12.05%, annual 11.23% (with
the earlier fleet-wide geothermal spread: 72.01%, 63.15%, 54.04%). For 2015-2025 alone: hourly
12.48%, monthly 11.82%, annual 10.96% (10.1% to 12.2% by year); 2025 10.2% and partial 2026
14.1% (annual). Sources: `docs/validation/ipcc_uncertainty_by_island_{hour,month,year}_montecarlo.csv`.
Approach 1 (analytic) gives 12.9% against Approach 2's 12.8% hourly, with no negative lower bound
in any hour (`docs/validation/geothermal_sigma_sensitivity.csv`, row "as shipped"), but formally
fails the IPCC coefficient-of-variation test (section 8), so Approach 2 is the reported method.

## 8. Known limitations

- Huntly gas portion and 2015 Q1-Q2 coal share rest on Genesis quarterly figures and the Rankine
  heat rate (estimates; `HUNTLY_GAS_PORTION_EF`, `HUNTLY_COAL_YYYYQn`).
- Stratford stays pooled under one generator code; bounds in the Stratford columns (`STRATFORD_BOUND_*`).
- Geothermal intensities for 2025 are operator-stated FY25 values; Mercury's are read from a chart
  (about +/-1 g/kWh). Mercury's stated intensities imply station generation 22% to 48% above
  metered export for Ngā Tamariki, Mōkai and Rotokawa (Ngā Tamariki also 22% above Mercury's own
  reported 688 GWh); Mercury does not state its denominator. Stations without FY25 figures hold
  2024; 2026 months take the nearest published year (`fuel_attribution.py`, `_nzga_nearest`). FY25
  is July-June, not the calendar year.
- Gas factor uncertainty is an estimate built from two sourced terms (section 7a); it is a Tier-1
  carbon range plus an empirical heat-rate term, not a plant-by-plant measurement. Geothermal
  step 1 uses the NIR category-level 7.07% for every station (no station-specific measurement
  uncertainty is published).
- Geothermal step 2: s_station counts reinjection step changes as year-to-year variation (Te Huka
  24 to 4 g/kWh in 2024, Ngāwhā OEC1-3 to 0 in 2023), so their step-2 sigmas (Te Huka 36.58%,
  Ngāwhā OEC1-3 39.99%) are conservative (`docs/validation/geo_step2_station_variation.csv`).
- Approach 1 formally fails the IPCC coefficient-of-variation test (30% limit) because of the
  steps 3-4 geothermal term (93.97%), although it agrees with Approach 2 (12.9% against 12.8% NI
  mean hourly band, no negative lower bound in any hour; `geothermal_sigma_sensitivity.csv`), so
  Monte Carlo (Approach 2) is the reported method.
- Data files over 100 MB (for example `output/edgs/edgs_hourly_generation*.parquet`,
  `output/edgs/edgs_hourly_emission_factor_primary.parquet`, and
  `output/zone_historical/zone_ef_TP_2015_2025.parquet`, 242 MB, from the separate zone-database
  commit 07c595e; sizes in `DATA_MANIFEST.csv` for the database files) cannot
  be pushed to GitHub (100 MB per-file limit); publication will need a data deposit (for example
  a DOI-minting repository), with `DATA_MANIFEST.csv` (path, size, SHA-256) as the integrity check.
- EDGS hourly shape templates (2017, 2021, 2023, 2024) are built from raw Generation_MD without
  the fills; the fills are 2.7% of NI geothermal in 2017 (norskeskog) and 1.1%, 4.8% and 3.9% of
  NI hydro in 2021, 2023 and 2024 (Matahina), at most 6.0% of NI hydro in any month; 0.15% to
  0.88% of national generation (`edgs_pipeline/build_edgs_hourly_shape.py`; `output/filled_generation_summary.csv`,
  `output/monthly_fuel_mix_NI_SI.csv`). The shapes are normalised per island and fuel and annual
  volumes come from MBIE.
- KAW0111 (`kawerau`) is Te Ahi O Maui net of about 11 MW local load; KAW0112 (`norskeskog`) may
  include Oji wood cogeneration from April 2023, unconfirmed (`GEO_MAP_kawerau`, `GEO_MAP_norskeskog`).
- The E3P/P40 September 2020 fill is 11.6% above the Genesis quarterly gas figure once Rankine gas
  is removed (`FILLCHECK_HLY2201_2020_09`).
- Roaring Meg is not measurable in Generation_MD or Grid_import (CML0331) and is absent.
- Real zero-output months remain (completeness check E6, `output/completeness_flags.csv`).
- Cogeneration: export only (section 2). Consumption side inherits every generation-side limitation.
- Projection: MBIE's accounting boundary changes at 2023/2024 (projected totals equal combustion
  only), so the consistent-scope variant does not reproduce MBIE totals by construction
  (`output/edgs/consistent_scope/NOTES.md`); grid denominator uses one grid share for both islands
  and MBIE's factor to four decimals; Glenbrook-class coal assumed inside MBIE's coal before 2032.
- TIMES-NZ is used as a comparison on the combustion side only (`reference_data/times_nz_3/README.md`).
