"""
Geothermal point-value correction (Item 2, "hybrid" version, 2026-09-14).

Background: this project's own plant register (`EA data/Dispatched generation
plant.csv`) assigns ONE flat value -- 99.996 kg/MWh (identical HeatRate x
EmissionsFactor) -- to every one of its 15 geothermal POCs (18 register rows,
counting duplicate/multi-unit entries). McLean & Richardson (2019, NZGA) give real,
field-measured 2018 emission intensities for 12 named NZ geothermal stations
(archived at docs/validation/../validation_references/McLean_NZGA_GeothermalGHG.pdf;
cross-checked in docs/validation/run_ipcc_uncertainty_full_coverage.py -- reproduces
their own published 76.03 gCO2/kWh MW-weighted mean before being trusted further).

Matching this project's 18 GEO register rows (by PlantCode/PlantName identity,
since some POCs host more than one physically distinct station -- e.g. WRK0331
hosts both Rotokawa and Te Huka under one connection point) against those 12
stations found:
  - 12 of 18 rows match a real station directly (92.1% of 2015-2025 geothermal
    generation, verified against output/plant_level_generation_emissions_2015_2025.csv).
  - 6 of 18 rows have NO match: all are newer than the 2018 study --
    Tauhara (commissioned 2023, 174 MW -- the single largest unmatched block),
    Ngawha B (2020), Te Ahi O Maui (2018), Kawerau TOPP2, and the Kawerau
    industrial cogeneration units (Norske Skog / Carter Holt Harvey, both under
    one PlantCode) -- 7.9% of 2015-2025 geothermal generation.

Hybrid rule: real per-station EF where matched; McLean & Richardson's own
MW-weighted fleet mean (76.03 kg/MWh, numerically = gCO2/kWh) as the fallback for
the unmatched 6 -- a real, sourced improvement on the flat 99.996 kg/MWh
assumption for all 18, without overstating how much of the register this single
2018 field study can actually speak to.

This does NOT touch or re-litigate the EDGS forward-looking pipeline's own,
separate, already-decided rejection of this same source (a different pipeline,
a different use of the data -- see run_ipcc_uncertainty_full_coverage.py docstring).
"""

GEOTHERMAL_FALLBACK_EF_KG_PER_MWH = 76.03  # McLean & Richardson (2019) MW-weighted fleet mean

# Keyed by the plant register's own PlantCode (PointOfConnectionCode + UnitCode,
# e.g. "WRK0331 RKA0") since it is the finest-grained identity key the register
# offers and is unique per physical unit/station even where POC is shared.
GEOTHERMAL_EF_KG_PER_MWH_BY_PLANTCODE = {
    # --- Matched to a real McLean & Richardson (2019) station ---
    "KAW1101 KAG0": 123.0,   # Kawerau -> their "Kawerau (KGL)" (104 MW, 123 gCO2/kWh)
    "NAP2201 NAP0": 63.0,    # Nga Awa Purua -> their "Nga Awa Purua (NAP)" (141 MW, 63)
    "NAP2202 NTM0": 64.0,    # Nga Tamariki -> their "Ngatamariki" (90 MW, 64)
    "OKI2201 OKI0": 341.0,   # Ohaaki -> their "Ohaaki" (31 MW, 341)
    "PPI2201 PPI0": 38.0,    # Poihipi -> their "Poihipi" (46 MW, 38)
    "THI2201 THI1": 43.0,    # Te Mihi 1 -> their "Te Mihi" (157 MW, 43)
    "THI2201 THI2": 43.0,    # Te Mihi 2 -> their "Te Mihi" (157 MW, 43)
    "WKM2201 MOK0": 52.0,    # Mokai -> their "Mokai" (56 MW, 52)
    "WRK0331 RKA0": 84.0,    # Rotokawa -> their "Rotokawa" (33 MW, 84)
    "WRK0331 TAA0": 45.0,    # Te Huka (original unit) -> their "Te Huka" (22 MW, 45)
    "WRK2201 WRK0": 21.0,    # Wairakei -> their "Wairakei A&B and binary" (116 MW, 21)
    # --- No match (post-dates the 2018 study, or an industrial cogen not in their
    #     station list) -- fallback to the fleet mean, not the old flat 99.996 ---
    "KAW0111 TAM0": GEOTHERMAL_FALLBACK_EF_KG_PER_MWH,  # Kawerau (Te Ahi O Maui), commissioned 2018
    "KAW0112 ONU0": GEOTHERMAL_FALLBACK_EF_KG_PER_MWH,  # Norske Skog / Carter Holt Harvey cogen
    "KAW2201 TAM0": GEOTHERMAL_FALLBACK_EF_KG_PER_MWH,  # Kawerau (TOPP2)
    "KOE1101 NGB0": GEOTHERMAL_FALLBACK_EF_KG_PER_MWH,  # Ngawha B, commissioned 2020
    "TAB0331 TAC0": GEOTHERMAL_FALLBACK_EF_KG_PER_MWH,  # Te Huka 3, commissioned 2024
    "TAB2201 TAB0": GEOTHERMAL_FALLBACK_EF_KG_PER_MWH,  # Tauhara, commissioned 2023 (174 MW)
}


def apply_geothermal_ef_correction(plant_df, plantcode_col="PlantCode", fuelcode_col="FuelCode",
                                    ef_col="EF_kg_per_MWh"):
    """Overrides ef_col in-place for every GEO row of plant_df using the hybrid
    McLean & Richardson (2019) mapping above. Raises if a GEO PlantCode is present
    in plant_df that this mapping doesn't cover (e.g. a newly registered geothermal
    POC), rather than silently leaving it at the register's own flat value."""
    is_geo = plant_df[fuelcode_col] == "GEO"
    geo_codes = set(plant_df.loc[is_geo, plantcode_col].unique())
    unmapped = geo_codes - set(GEOTHERMAL_EF_KG_PER_MWH_BY_PLANTCODE)
    if unmapped:
        raise ValueError(
            f"geothermal_ef_correction: {len(unmapped)} GEO PlantCode(s) not covered by the "
            f"McLean & Richardson hybrid mapping -- extend GEOTHERMAL_EF_KG_PER_MWH_BY_PLANTCODE "
            f"before re-running: {sorted(unmapped)}"
        )
    plant_df.loc[is_geo, ef_col] = plant_df.loc[is_geo, plantcode_col].map(
        GEOTHERMAL_EF_KG_PER_MWH_BY_PLANTCODE
    )
    return plant_df
