"""
Phase 3: four-tier error decomposition + load-shape + scenario/
start-year sensitivity.

Design choices:
  1. Headline series = generation-side EF (NI). Consumption-side (gross-up
     corrected for the ~7.7% accounting-basis artefact found in Phase 2 S2.1)
     run as a one-row sensitivity check only, not a full re-run.
  2. Headline start year = 2027; sensitivity across {2025, 2027, 2030}.
  3. Three STYLISED load shapes (no BEES/metered data found in project).
  4. Four treatments:
       (a) full hourly, island-resolved, scenario EF
       (b) annual island EF (constant within year, still island-specific, still
           year-by-year trajectory)
       (c) annual NATIONAL EF (constant within year, blended across islands,
           still year-by-year trajectory)
       (d) static base-year NATIONAL EF (held constant for the entire study
           period, at the assessment start year's level)
     Key simplification (used deliberately for speed and clarity): since
     building load weights within a year always sum to 1, treatments (b),(c),(d)
     collapse to simple ANNUAL SCALARS (the load-weighted average of a constant
     is that constant) -- only treatment (a) requires real hourly load x EF
     computation. This is mathematically exact, not an approximation.
  Decomposition (chosen order): total = d - a = (b-a) [temporal] + (c-b)
  [spatial] + (d-c) [trajectory]. An alternate order (spatial-first) is also
  computed to test order-sensitivity.
"""
import os

import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGS = ROOT / "output" / "edgs"
TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"

# Template parameterisation: set EDGS_TEMPLATE_YEAR to re-derive this
# decomposition against a non-central Assumption-1 shape template, matching the
# convention Modules 5-6 use. Default 2021 = the central template, with the
# default input and output paths. Non-central runs read edgs_*_tmpl<year>.parquet
# and write phase3_*_tmpl<year>.csv, so the central outputs are not overwritten.
# This tests whether the spatial > temporal ranking is a property of the grid or
# an artefact of the template year.
TEMPLATE_YEAR = int(os.environ.get("EDGS_TEMPLATE_YEAR", "2021"))
SUFFIX = "" if TEMPLATE_YEAR == 2021 else f"_tmpl{TEMPLATE_YEAR}"

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

log(f"Assumption-1 shape template: {TEMPLATE_YEAR}"
    f"{' (central)' if not SUFFIX else ' (sensitivity run, suffix ' + SUFFIX + ')'}")

SCENARIOS = ["Reference", "Growth", "Constraint", "Innovation", "Environmental"]
BUILDING_ISLAND = "NI"  # most NZ commercial floor area (Auckland, Wellington); SI noted qualitatively only
STUDY_PERIODS = [10, 25, 30, 50]  # yrs; justified: 10=short lease/fitout cycle,
# 25=common NZ building-LCA reporting horizon (aligned with EN15978/typical RICS
# whole-life carbon assessment practice as applied in NZ), 30=NZGBC Green Star
# reference study period, 50=NZ Building Code intended structural life (B1/AS1)
# and common "whole-of-life" LCA convention.
START_YEARS = [2025, 2027, 2030]
HEADLINE_START = 2027

# Load EF data (generation-side, NI+SI) and generation weights (for computing
# annual island/national EF -- generation-weighted, i.e. the physically correct
# way to average an intensity over a year of varying output).
ef = pd.read_parquet(EDGS / f"edgs_hourly_emission_factor{SUFFIX}.parquet")
ef = ef[(ef["ef_basis"] == "generation") & (ef["island"].isin(["NI", "SI"]))].copy()
ef["year"] = ef["datetime_hour"].dt.year
ef["dow"] = ef["datetime_hour"].dt.dayofweek
ef["hour"] = ef["datetime_hour"].dt.hour
log(f"Loaded {len(ef)} generation-side NI/SI hourly EF rows")

gen = pd.read_parquet(EDGS / f"edgs_hourly_generation{SUFFIX}.parquet")
gen_isl = gen.groupby(["scenario", "island", "datetime_hour"], observed=True)["generation_mwh"].sum().reset_index()

efw = ef.merge(gen_isl, on=["scenario", "island", "datetime_hour"], how="left")

# Annual island EF (b), generation-weighted (reuse Phase 1 logic)
def wmean(g):
    w = g["generation_mwh"].fillna(0)
    return np.average(g["emission_factor_kg_co2e_per_kwh"], weights=w) if w.sum() > 0 else np.nan

annual_island = (efw.groupby(["scenario", "island", "year"])
                 .apply(lambda g: pd.Series({"annual_island_ef": wmean(g)}), include_groups=False)
                 .reset_index())

# Annual NATIONAL generation-side EF (c): pool NI+SI CO2 and generation
efw["co2_kg"] = efw["emission_factor_kg_co2e_per_kwh"] * efw["generation_mwh"].fillna(0) * 1000
nat_hourly = efw.groupby(["scenario", "datetime_hour"]).agg(
    co2_kg=("co2_kg", "sum"), gen_mwh=("generation_mwh", "sum")).reset_index()
nat_hourly["national_ef"] = nat_hourly["co2_kg"] / (nat_hourly["gen_mwh"] * 1000)
nat_hourly["year"] = nat_hourly["datetime_hour"].dt.year
annual_national = (nat_hourly.groupby(["scenario", "year"])
                   .apply(lambda g: pd.Series({"annual_national_ef": np.average(g["national_ef"], weights=g["gen_mwh"])}),
                          include_groups=False).reset_index())

annual_island.to_csv(TABLES / f"phase3_annual_island_ef{SUFFIX}.csv", index=False)
annual_national.to_csv(TABLES / f"phase3_annual_national_ef{SUFFIX}.csv", index=False)
log(f"Computed annual island EF ({len(annual_island)} rows) and annual national EF ({len(annual_national)} rows)")

# Load shapes: map (dow,hour) raw intensity onto each actual calendar year,
# normalised to sum exactly 1.0 for THAT year (handles leap years exactly).
shapes = pd.read_csv(TABLES / "phase3_load_shapes_stylised.csv")
SHAPE_LABELS = shapes["label"].unique().tolist()
log(f"Load shapes: {SHAPE_LABELS}")

ef_ni = ef[ef["island"] == BUILDING_ISLAND].copy()
ef_ni_national = nat_hourly.copy()  # for the "swap island->national but keep hourly" alt-order term

log("\nPrecomputing load-weighted annual EF for every (shape, scenario, year, source) "
    "combination once, to avoid redundant recomputation across overlapping study periods...")
ef_ni_national2 = ef_ni_national.copy()
ef_ni_national2["dow"] = ef_ni_national2["datetime_hour"].dt.dayofweek
ef_ni_national2["hour"] = ef_ni_national2["datetime_hour"].dt.hour

cache = {}
for shape_label in SHAPE_LABELS:
    shp = shapes[shapes["label"] == shape_label][["dow", "hour", "raw_intensity"]]
    # island source
    m_isl = ef_ni.merge(shp, on=["dow", "hour"], how="left")
    isl_res = (m_isl.groupby(["scenario", "year"])
               .apply(lambda g: np.average(g["emission_factor_kg_co2e_per_kwh"], weights=g["raw_intensity"]),
                      include_groups=False))
    for (scenario, year), val in isl_res.items():
        cache[(shape_label, scenario, year, "island")] = val
    # national source
    m_nat = ef_ni_national2.merge(shp, on=["dow", "hour"], how="left")
    nat_res = (m_nat.groupby(["scenario", "year"])
               .apply(lambda g: np.average(g["national_ef"], weights=g["raw_intensity"]),
                      include_groups=False))
    for (scenario, year), val in nat_res.items():
        cache[(shape_label, scenario, year, "national")] = val
    log(f"  cached shape={shape_label}: {len(isl_res)} island + {len(nat_res)} national (scenario,year) entries")

def load_weighted_annual_ef(shape_label, scenario, year, source="island"):
    return cache[(shape_label, scenario, year, source)]

# Headline decomposition (Reference, NI, start=2027, all 4 study
# periods, all 3 load shapes) + order-sensitivity check.
log("\n" + "=" * 70)
log("ITEM 14: four-tier error decomposition, headline (Reference, NI, start=2027)")
log("=" * 70)

log("\n--- Study-period feasibility vs. the EDGS projection horizon (2024-2050) ---")
log("Per user decision (2026-08-02): truncate combinations losing <=20%% of the "
    "requested period (label explicitly); DROP 50-year periods entirely (out of "
    "scope for this dataset, all start years); drop any other combination losing "
    ">20%% by the same logic. This is a genuine DATASET boundary (MBIE's own EDGS "
    "2024 horizon ends 2050), not a methodological choice -- feeds Phase 4 item 20 "
    "limitations and is flagged as a natural re-run point for a future MBIE update.")
FEASIBLE = {}
for start_year in START_YEARS:
    for L in STUDY_PERIODS:
        avail_end = min(start_year + L - 1, 2050)
        n_years = avail_end - start_year + 1
        loss_frac = (L - n_years) / L
        if L == 50 or loss_frac > 0.20:
            status = "out_of_scope"
        elif n_years < L:
            status = f"truncated_{n_years}yrs"
        else:
            status = "full"
        FEASIBLE[(start_year, L)] = (n_years, status)
        log(f"  start={start_year} L={L}: covers {start_year}-{avail_end} "
            f"({n_years} yrs, {100*loss_frac:.0f}%% lost) -> {status}")

decomp_rows = []
for shape_label in SHAPE_LABELS:
    for scenario in SCENARIOS:
        for start_year in START_YEARS:
            base_national_ef = annual_national[(annual_national["scenario"] == scenario) &
                                                (annual_national["year"] == start_year)]["annual_national_ef"].values[0]
            for L in STUDY_PERIODS:
                n_years, fit_status = FEASIBLE[(start_year, L)]
                if fit_status == "out_of_scope":
                    continue
                years = list(range(start_year, start_year + n_years))
                a_vals, b_vals, c_vals, aprime_vals = [], [], [], []
                for y in years:
                    a = load_weighted_annual_ef(shape_label, scenario, y, source="island")
                    aprime = load_weighted_annual_ef(shape_label, scenario, y, source="national")
                    b = annual_island[(annual_island["scenario"] == scenario) & (annual_island["island"] == BUILDING_ISLAND) &
                                       (annual_island["year"] == y)]["annual_island_ef"].values[0]
                    c = annual_national[(annual_national["scenario"] == scenario) & (annual_national["year"] == y)]["annual_national_ef"].values[0]
                    a_vals.append(a); b_vals.append(b); c_vals.append(c); aprime_vals.append(aprime)
                E_a = sum(a_vals)     # cumulative, per unit annual building energy
                E_b = sum(b_vals)
                E_c = sum(c_vals)
                E_d = base_national_ef * n_years  # static EF x ACTUAL years used (truncation-consistent)
                E_aprime = sum(aprime_vals)

                temporal = E_b - E_a
                spatial = E_c - E_b
                trajectory = E_d - E_c
                total = E_d - E_a

                # alt order: spatial-first
                spatial_alt = E_aprime - E_a
                temporal_alt = E_c - E_aprime
                trajectory_alt = E_d - E_c
                total_alt = E_d - E_a

                decomp_rows.append({
                    "load_shape": shape_label, "scenario": scenario, "start_year": start_year,
                    "study_period_yrs_requested": L, "fit_status": fit_status, "n_years_used": n_years,
                    "E_a_hourly_island": E_a, "E_b_annual_island": E_b,
                    "E_c_annual_national": E_c, "E_d_static_base": E_d,
                    "total_error_d_minus_a": total,
                    "temporal_component": temporal, "spatial_component": spatial, "trajectory_component": trajectory,
                    "temporal_pct_of_total": 100 * temporal / total if total else np.nan,
                    "spatial_pct_of_total": 100 * spatial / total if total else np.nan,
                    "trajectory_pct_of_total": 100 * trajectory / total if total else np.nan,
                    "total_error_pct_of_Ea": 100 * total / E_a if E_a else np.nan,
                    "spatial_alt_component": spatial_alt, "temporal_alt_component": temporal_alt,
                    "order_check_total_matches": abs(total - total_alt) < 1e-9,
                })

decomp = pd.DataFrame(decomp_rows)
decomp.to_csv(TABLES / f"phase3_decomposition_full{SUFFIX}.csv", index=False)
log(f"Wrote phase3_decomposition_full{SUFFIX}.csv ({len(decomp)} rows)")

log("\n=== Headline: Reference, NI, start=2027, daytime_office load shape ===")
hl = decomp[(decomp["scenario"] == "Reference") & (decomp["start_year"] == HEADLINE_START) &
            (decomp["load_shape"] == "daytime_office")]
log(hl[["study_period_yrs_requested", "fit_status", "E_a_hourly_island", "E_d_static_base", "total_error_pct_of_Ea",
        "temporal_pct_of_total", "spatial_pct_of_total", "trajectory_pct_of_total"]].to_string(index=False))

log("\n=== Order-sensitivity check: does temporal-first vs spatial-first give materially different splits? ===")
comp = decomp[(decomp["scenario"] == "Reference") & (decomp["start_year"] == HEADLINE_START) & (decomp["load_shape"] == "daytime_office")].copy()
comp["spatial_first_pct"] = 100 * comp["spatial_alt_component"] / comp["total_error_d_minus_a"]
comp["temporal_first_pct_orig_order"] = comp["temporal_pct_of_total"]
comp["temporal_alt_pct"] = 100 * comp["temporal_alt_component"] / comp["total_error_d_minus_a"]
log(comp[["study_period_yrs_requested", "fit_status", "temporal_pct_of_total", "spatial_pct_of_total",
          "spatial_first_pct", "temporal_alt_pct"]].to_string(index=False))
log(f"All order-check totals match exactly (telescoping confirmed): {decomp['order_check_total_matches'].all()}")

with open(LOGS / f"phase3_decomposition_log{SUFFIX}.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("\nDone.")
