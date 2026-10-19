"""
edgs_common.py — shared reference data for the forward-looking EDGS 2024
hourly, island-resolved reconstruction (Modules 1-6).

Everything here is either (A) a direct MBIE workbook reference, (B) part of
Assumption 1 / Assumption 2, or (C) an externally-cited constant (the MfE fuel
emission factors). Nothing is invented; every constant carries a source string.

Traceability tags used across the pipeline output:
    MBIE_annual_disaggregated | assumption_1 | assumption_2 | calculated
"""
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent  # edgs_pipeline/ itself -- files that moved alongside this script
ROOT = Path(__file__).parent.parent  # repo root (this file now lives in edgs_pipeline/, one level deeper -- 2026-08-12 reorg)
OUT_DIR = ROOT / "output" / "edgs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# MBIE source files (verified present this session) -- local to edgs_pipeline/,
# not repo-root: moved here 2026-08-12, only ever read by scripts in this folder
# ---------------------------------------------------------------------------
RESULTS_XLSX = SCRIPT_DIR / "EDGS_2024_Results.xlsx"
ASSUMPTIONS_XLSX = SCRIPT_DIR / "electricity-demand-generation-scenarios-2024-assumptions.xlsx"

# Historical hourly shape (Assumption 1 source) — produced by the existing
# historical pipeline in this same folder.
HIST_OUT = ROOT / "output"
# Path fixed 2026-08-11: was "Consumption/output" (stale after the 2026-08-10 reorg
# renamed the folder to Consumption_Island/ — this reference was never updated, so any
# fresh run of Module 4's demand-shape step would have hit FileNotFoundError; caught
# while rebuilding the shape templates for PLAN_11YEAR_TEMPLATE_REASSESSMENT.md).
CONSUMPTION_OUT = ROOT / "Consumption_Island" / "output"

SCENARIOS = ["Reference", "Growth", "Constraint", "Innovation", "Environmental"]
YEARS = list(range(2024, 2051))

# ---------------------------------------------------------------------------
# Region -> Island (Generation Stack `Region` field, 14 NZ regional councils).
# The only island tag for EXISTING plants. New-build plants use the GEM build
# schedule `Island` field directly (see Module 2).
# ---------------------------------------------------------------------------
REGION_TO_ISLAND = {
    # North Island
    "Northland": "NI", "Auckland": "NI", "Waikato": "NI", "Bay of Plenty": "NI",
    "Gisborne": "NI", "Hawke's Bay": "NI", "Taranaki": "NI",
    "Manawatū-Whanganui": "NI", "Wellington": "NI",
    # South Island
    "Nelson": "SI", "Marlborough": "SI", "West Coast": "SI", "Canterbury": "SI",
    "Otago": "SI", "Southland": "SI",
}

# ---------------------------------------------------------------------------
# Fuel crosswalk: MBIE Commodity (Results `Electricity generation`.Commodity)
#   <-> historical FUEL_STD (build_ef_timeseries.py) <-> dispatch class.
#
# dispatch_class:
#   "renewable" -> must-run, shaped to hourly by Assumption 1 (Module 4),
#                  ranked ahead of thermal, not merit-order competed.
#   "thermal"   -> merit-order dispatched against residual load (Module 5),
#                  carries a fuel CO2-e factor.
#   "storage"   -> Demand side response / batteries: Assumption 2 only.
# ---------------------------------------------------------------------------
COMMODITY = {
    # commodity            : (fuel_std, dispatch_class)
    "Hydro":                ("HYD",  "renewable"),
    "Wind":                 ("WIN",  "renewable"),
    "Solar":                ("SOL",  "renewable"),
    "Geothermal":           ("GEO",  "renewable"),
    "Biogas":               ("BGS",  "renewable"),
    "Wood":                 ("WOOD", "renewable"),
    "Waste heat":           ("WHT",  "renewable"),
    "Coal":                 ("CLG",  "thermal"),
    "Natural gas":          ("GAS",  "thermal"),
    "Diesel":               ("DSL",  "thermal"),
    "LPG":                  ("LPG",  "thermal"),
    "Fuel oil":             ("FO",   "thermal"),
    "Demand side response": ("DSR",  "storage"),
}
RENEWABLE_COMMODITIES = [c for c, (_, k) in COMMODITY.items() if k == "renewable"]
THERMAL_COMMODITIES = [c for c, (_, k) in COMMODITY.items() if k == "thermal"]

# Generation Stack `Tech` code -> MBIE Commodity (for the plant register).
TECH_TO_COMMODITY = {
    "HydRR": "Hydro", "HydPK": "Hydro", "HydSC": "Hydro",
    "Wind": "Wind", "Solar": "Solar", "Geo": "Geothermal",
    "Wood": "Wood", "BioRecip": "Biogas",
    "Coal": "Coal",
    "CCGT": "Natural gas", "OCGT": "Natural gas", "GasPkr": "Natural gas",
    "GasCog": "Natural gas", "OthCog": "Natural gas",
    "DslPkr": "Diesel",
}

# ---------------------------------------------------------------------------
# MfE fuel emission factors — EXTERNAL, CITED (brief Section 1.3).
#
# Source: Ministry for the Environment (2024), "Measuring emissions: A guide for
#   organisations: 2024 detailed guide", publication ME1829.
#   - Table 3  "Emission factors for the stationary combustion of fuels"
#              (kg CO2-e/unit, combined CO2+CH4+N2O, Industrial use rows).
#   - Table A2 "Underlying data used to calculate fuel emission factors"
#              (net calorific value MJ/unit; gross GHG factors from Annex 4 of
#               New Zealand's Greenhouse Gas Inventory 1990-2022).
#
# Values below are kg CO2-e per GJ of fuel INPUT (net/lower calorific basis),
# consistent with the Generation Stack heat rate unit (GJ/GWh). Natural gas is
# published directly per GJ; the others are Table-3 kg CO2-e/unit divided by the
# Table-A2 calorific value (GJ/unit). Derivation shown per fuel.
#
# Cross-check against the historical pipeline (build_ef_timeseries.py):
#   gas 54.0 x ~7150 GJ/GWh  ~= 386 kg/MWh (matches Huntly HLY5 gas 386)
#   coal 92.6 x ~10700 GJ/GWh ~= 994 kg/MWh (matches Huntly Rankine coal 994)
# ---------------------------------------------------------------------------
MFE_SOURCE = ("MfE 2024 Measuring Emissions Detailed Guide (ME1829), "
              "Table 3 + Table A2 (Industrial use, net CV basis)")

MFE_FUEL_EF_KG_PER_GJ = {
    # commodity : (kg CO2-e/GJ, derivation note)
    "Natural gas": (54.0,  "Table 3 industrial, Natural gas GJ row: 54.0 kg CO2-e/GJ"),
    "Coal":        (92.6,  "Table 3 industrial sub-bituminous 2.00 kg/kg / Table A2 CV 21.64 MJ/kg"),
    "Diesel":      (69.4,  "Table 3 industrial 2.67 kg/litre / Table A2 CV 38.49 MJ/litre"),
    "LPG":         (59.4,  "Table 3 industrial 2.97 kg/kg / Table A2 CV 50.00 MJ/kg"),
    "Fuel oil":    (74.9,  "Table 3 industrial heavy fuel oil 3.05 kg/litre / Table A2 CV 40.74 MJ/litre"),
}


def fuel_ef_kg_per_gj(commodity: str) -> float:
    """kg CO2-e per GJ fuel input for a thermal commodity; 0.0 for non-thermal."""
    v = MFE_FUEL_EF_KG_PER_GJ.get(commodity)
    return float(v[0]) if v else 0.0


# ---------------------------------------------------------------------------
# Wood/biomass non-biogenic CH4+N2O factor — EXTERNAL, CITED (Brief P/Q).
#
# Source: Ministry for the Environment (2024), "Measuring emissions: A guide for
#   organisations: 2024 detailed guide" (ME1829), Table 3.4 "Biofuels and Biomass
#   Emission Factors", "Biomass - Manufacturing Use" category (industrial-scale
#   combustion, matching a utility boiler such as the converted Huntly Rankine units --
#   NOT the "Commercial Use" category, which is for small-scale/less-complete combustion
#   and carries a materially higher factor).
#
# CO2 from biomass combustion is correctly biogenic (zero-rated under this guide's own
# convention, and under the pipeline's existing "Non-combustion fuels... excluded from
# the combustion sum" treatment) and is NOT included here -- this is the CH4+N2O
# non-biogenic residual ONLY, additive to (not a replacement for) the zero-rated CO2.
#
# Cross-checked across three published wood forms; all three reduce to the SAME
# underlying per-GJ rate (confirming one consistent factor, not a fuel-form-specific
# fit -- gross calorific values as stated by the guide):
#   Wood-Chips:   0.023028  kg CO2-e/kg / 15.150 MJ/kg = 1.5200 kg CO2-e/GJ
#   Wood-Pellets: 0.0288618 kg CO2-e/kg / 18.988 MJ/kg = 1.5200 kg CO2-e/GJ
#   Wood-Green:   0.0135098 kg CO2-e/kg /  8.888 MJ/kg = 1.5200 kg CO2-e/GJ
#
# Tested (Brief P) against the actual incremental Wood PJ at the Huntly Rankine
# biomass-conversion event: closes ~15% of the post-2032 Environmental/Innovation
# Check-2a gap on average (max ~32%, 2032) -- a real, partial, non-adopted-until-now
# contributor. Adopted into combustion_co2_kg's companion wood_nonco2_kg (Brief Q).
# ---------------------------------------------------------------------------
WOOD_NONBIOGENIC_KG_PER_GJ = 1.5200
WOOD_NONBIOGENIC_SOURCE = ("MfE 2024 Measuring Emissions Detailed Guide (ME1829), Table 3.4 "
                           "'Biofuels and Biomass Emission Factors', Biomass - Manufacturing Use "
                           "(CH4+N2O only; CO2 is biogenic and correctly excluded, unchanged)")


# ---------------------------------------------------------------------------
# Geothermal fugitive CO2-e factor — EXTERNAL, CITED (follow-up brief Step 1).
#
# Diagnosed (build_edgs_check2_diagnostic.py): the residual Check-2 gap (MBIE electricity
# GHG minus MfE combustion CO2) is explained by geothermal, NOT biomass (biomass rejected:
# implausible implied factor, R2=0.43, coefficient goes negative once geothermal enters).
# Regression-implied factor: 77.4 g CO2/kWh, R2=0.9995 across all 135 scenario-years.
#
# Source (field-level, 2018 data): McLean, K., Richardson, I. (2019). "Greenhouse Gas
#   Emissions from New Zealand Geothermal Power Generation in Context." Proceedings 41st
#   New Zealand Geothermal Workshop, 25-27 Nov 2019, Auckland. Table: gCO2-eq/kWh(net) by
#   power station, 2018 MW-weighted-average operational data.
# Fleet MW-weighted average (2018): 76 g CO2-e/kWh — within 2% of the regression-implied
# 77.4 g/kWh. This closeness is corroborating evidence for the diagnosis, not proof the
# specific number is the mechanism; field-level data (below) is used in preference to the
# flat average wherever a plant can be identified.
#
# Field-specific values (g CO2-e/kWh net, McLean & Richardson 2019, 2018 data):
GEOTHERMAL_FIELD_EF_G_PER_KWH = {
    "Wairakei": 21, "Te Mihi": 43, "Poihipi": 38, "Ohaaki": 341, "Te Huka": 45,
    "Rotokawa": 84, "Nga Awa Purua": 63, "Mokai": 52, "Ngatamariki": 64,
    "Kawerau_KGL": 123, "Kawerau_TOPP1": 60, "Ngawha": 304,  # Ngawha: PRE-reinjection value
}
GEOTHERMAL_FLEET_AVG_G_PER_KWH = 76.0  # 2018 MW-weighted average; fallback for unnamed/new fields

# Ngawha override: Top Energy's Ngawha Carbon Zero Project achieved 100% non-condensable-gas
# reinjection; emissions from the first two stations ceased Jan 2023, the third by end 2023
# (source: Ngawha Generation Ltd, "Our path to net carbon zero by 2025" / ThinkGeoEnergy,
# "Ngawha becomes New Zealand's first zero-carbon geothermal power station"). Since ALL EDGS
# scenario years are 2024-2050 (post-2023), Ngawha plants use 0 g/kWh throughout, not the
# pre-reinjection 304 g/kWh — this is a dated, cited real-world operational change, not an
# invented adjustment.
NGAWHA_ZERO_FROM_YEAR = 2024

# Generation Stack plant name -> field key (existing/consented plants only; generic future
# plants not tied to a named field fall back to GEOTHERMAL_FLEET_AVG_G_PER_KWH).
GEOTHERMAL_PLANT_TO_FIELD = {
    "Wairākei A & B": "Wairakei", "Wairākei Binary": "Wairakei", "Wairākei C & D": "Wairakei",
    "Te Mihi": "Te Mihi", "Te Mihi (expansion)": "Te Mihi",
    "Poihipi Road": "Poihipi",
    "Ōhaaki": "Ohaaki",
    "Te Huka (Binary)": "Te Huka", "Te Huka Unit 3": "Te Huka",
    "Rotokawa": "Rotokawa",
    "Ngā Awa Pūrua": "Nga Awa Purua",
    "Mōkai": "Mokai",
    "Ngātamariki": "Ngatamariki", "Ngātamariki expansion": "Ngatamariki",
    "Kawerau": "Kawerau_KGL",
    "Kawerau (TOPP1)": "Kawerau_TOPP1", "Kawerau (TOPP2)": "Kawerau_TOPP1",
    "Ngāwhā Stage 1 & 2": "Ngawha", "Ngāwhā Stage 3 (OEC4)": "Ngawha",
    "Ngāwhā Stage 4 (OEC5)": "Ngawha", "Ngāwhā Expansion: Stage 5": "Ngawha",
    "Ngāwhā Expansion: Stage 6": "Ngawha",
    # No 2018 field data (newer or undeveloped fields): Te Ahi O Maui (~2020), Tauhara
    # (commissioned 2024+), Taheke/Reporoa/Tikitere/Mangakino/Tokaanu/Atiamuri (undeveloped
    # generic future fields) -> fleet-average fallback, flagged in source_detail.
}


def geothermal_ef_kg_per_mwh(plant_name: str, year: int) -> tuple:
    """(factor kg/MWh, source_detail) for one geothermal plant in one year."""
    field = GEOTHERMAL_PLANT_TO_FIELD.get(plant_name)
    if field == "Ngawha" and year >= NGAWHA_ZERO_FROM_YEAR:
        return 0.0, "Ngawha carbon-zero from 2023 (Top Energy NCG reinjection, cited)"
    if field and field in GEOTHERMAL_FIELD_EF_G_PER_KWH:
        g = GEOTHERMAL_FIELD_EF_G_PER_KWH[field]
        return g, f"McLean & Richardson 2019, field={field}, {g} g CO2-e/kWh (2018)"
    return GEOTHERMAL_FLEET_AVG_G_PER_KWH, "McLean & Richardson 2019 fleet MW-weighted average (fallback, unnamed field)"


# ---------------------------------------------------------------------------
# Retirement calendar — brief Section 2 (transcribed from the EDGS 2024 report
# Appendix One, which is not in the folder; the specific dates are given in the
# brief and cross-checked against Generation Stack commissioning fields).
# Keyed by scenario group. `default` applies to Reference/Growth/Constraint.
# ---------------------------------------------------------------------------
RETIREMENTS = {
    "default": {
        "Taranaki Combined Cycle": 2024,   # end of 2024
        "Huntly Unit 5": 2037,
        "Stratford peaker": 2053,
        # Huntly Rankine units: no fixed retirement in these scenarios
    },
    "Innovation": {
        "Taranaki Combined Cycle": 2024,
        "Huntly Unit 5": 2032,
        "Stratford peaker": 2035,
        "Huntly Rankine": ("biomass", 2032),  # converted to biomass from 2032
    },
    "Environmental": {
        "Taranaki Combined Cycle": 2024,
        "Huntly Unit 5": 2032,
        "Stratford peaker": 2035,
        "Huntly Rankine": ("biomass", 2032),
    },
}


def retirement_rules(scenario: str) -> dict:
    return RETIREMENTS.get(scenario, RETIREMENTS["default"])


# Assumption text (verbatim, brief Section 4/5) — embedded in every README.
ASSUMPTION_1 = (
    "Assumption 1 - Renewable/demand hourly shape. The diurnal and seasonal "
    "shape of demand and of hydro/wind/solar/geothermal generation, by island, "
    "observed in the user's historical hourly dataset (date range stated in "
    "metadata) is applied forward to all future years, scaled to MBIE's "
    "published annual totals and capacity additions. This does not capture "
    "future changes in weather, hydrology sequencing, or demand-shape shifts "
    "beyond MBIE's own annual peak-ratio assumptions.")
ASSUMPTION_2 = (
    "Assumption 2 - Battery/BESS hourly dispatch rule (model-original, NOT "
    "MBIE-derived). Charge from surplus renewable generation when residual load "
    "is negative or thermal marginal cost is at its minimum tier; discharge to "
    "reduce peak residual load, up to each year's total battery capacity from "
    "the Generation Stack / GEM build schedule.")

SOURCE_TAGS = {"MBIE_annual_disaggregated", "assumption_1", "assumption_2", "calculated"}


def log_factory():
    """Return (log, lines) — same logging idiom as the historical scripts."""
    lines = []

    def log(msg):
        print(msg)
        lines.append(str(msg))

    return log, lines
