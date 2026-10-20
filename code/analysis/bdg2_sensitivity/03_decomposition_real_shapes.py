"""
BDG2 real-data sensitivity test (script 3 of 4): re-run the same four-tier error
decomposition as the main NZ assessment (phase3_decomposition.py). Real,
hemisphere-shifted BDG2 building shapes replace the stylised
(daytime_office / continuous_24_7 / evening_weighted) shapes. The test asks
whether real hourly demand timing changes the decomposition's conclusions,
because demand timing can correlate with weather and weather correlates
with grid conditions.

Read-only with respect to the main assessment. The script reads
../../tables/phase3_annual_island_ef.csv and phase3_annual_national_ef.csv.
Treatments b/c/d are shape-independent, so reusing them keeps the
comparison with the main results like for like. Nothing is written back
into analysis_paper/tables, analysis_paper/figures, or any file the main
assessment produced. All new outputs go to
analysis_paper/sensitivity_realdata_bdg2/{tables,figures,logs}.
"""
import numpy as np
import pandas as pd
from pathlib import Path

MAIN_ROOT = Path(__file__).resolve().parents[3]  # .../Grid Emission Factor
MAIN_TABLES = MAIN_ROOT / "analysis_paper" / "tables"
EDGS = MAIN_ROOT / "output" / "edgs"

SELF_ROOT = Path(__file__).resolve().parents[1]  # .../sensitivity_realdata_bdg2
TABLES = SELF_ROOT / "tables"
LOGS = SELF_ROOT / "logs"

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

SCENARIOS = ["Reference", "Growth", "Constraint", "Innovation", "Environmental"]
BUILDING_ISLAND = "NI"
STUDY_PERIODS = [10, 25, 30, 50]
START_YEARS = [2025, 2027, 2030]
HEADLINE_START = 2027

# Load NZ hourly EF (read-only, released file, never modified)
ef = pd.read_parquet(EDGS / "edgs_hourly_emission_factor.parquet")
ef = ef[(ef["ef_basis"] == "generation") & (ef["island"] == BUILDING_ISLAND)].copy()
ef["year"] = ef["datetime_hour"].dt.year
ef["month"] = ef["datetime_hour"].dt.month
ef["dow"] = ef["datetime_hour"].dt.dayofweek
ef["is_weekend"] = ef["dow"] >= 5
ef["hour"] = ef["datetime_hour"].dt.hour
log(f"Loaded {len(ef)} NI generation-side hourly EF rows (read-only from the released output)")

# Load real BDG2 shapes (already hemisphere-shifted to nz_month by 02_build_real_shapes.py)
shapes = pd.read_csv(TABLES / "real_building_shapes_hemisphere_shifted.csv")
SHAPE_LABELS = shapes["building_id"].unique().tolist()
log(f"Real shapes: {SHAPE_LABELS}")

# Precompute load-weighted annual EF for every (shape, scenario, year):
# treatment (a), the only one that needs real hourly detail.
cache = {}
for shape_label in SHAPE_LABELS:
    shp = shapes[shapes["building_id"] == shape_label][["nz_month", "is_weekend", "hour", "norm_weight"]].rename(
        columns={"nz_month": "month"})
    m = ef.merge(shp, on=["month", "is_weekend", "hour"], how="left")
    n_unmatched = m["norm_weight"].isna().sum()
    if n_unmatched:
        log(f"  WARNING: {n_unmatched} unmatched hours for shape {shape_label} (filled with 0 weight)")
        m["norm_weight"] = m["norm_weight"].fillna(0)
    res = (m.groupby(["scenario", "year"])
           .apply(lambda g: np.average(g["emission_factor_kg_co2e_per_kwh"], weights=g["norm_weight"]),
                  include_groups=False))
    for (scenario, year), val in res.items():
        cache[(shape_label, scenario, year)] = val
    log(f"  cached shape={shape_label}: {len(res)} (scenario,year) entries")

# Load treatments (b)/(c)/(d) source data: read-only reuse of the main
# assessment's shape-independent annual island/national EF tables.
annual_island = pd.read_csv(MAIN_TABLES / "phase3_annual_island_ef.csv")
annual_island_ni = annual_island[annual_island["island"] == BUILDING_ISLAND]
annual_national = pd.read_csv(MAIN_TABLES / "phase3_annual_national_ef.csv")
log(f"\nRead (read-only) {MAIN_TABLES / 'phase3_annual_island_ef.csv'} and phase3_annual_national_ef.csv")

# Feasibility (same 2050-horizon truncation rule as the main assessment)
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
                a_vals, b_vals, c_vals = [], [], []
                for y in years:
                    a = cache[(shape_label, scenario, y)]
                    b = annual_island_ni[(annual_island_ni["scenario"] == scenario) &
                                         (annual_island_ni["year"] == y)]["annual_island_ef"].values[0]
                    c = annual_national[(annual_national["scenario"] == scenario) &
                                        (annual_national["year"] == y)]["annual_national_ef"].values[0]
                    a_vals.append(a); b_vals.append(b); c_vals.append(c)
                E_a, E_b, E_c = sum(a_vals), sum(b_vals), sum(c_vals)
                E_d = base_national_ef * n_years

                temporal = E_b - E_a
                spatial = E_c - E_b
                trajectory = E_d - E_c
                total = E_d - E_a

                decomp_rows.append({
                    "load_shape": shape_label, "scenario": scenario, "start_year": start_year,
                    "study_period_yrs_requested": L, "fit_status": fit_status, "n_years_used": n_years,
                    "E_a_hourly_island": E_a, "E_b_annual_island": E_b, "E_c_annual_national": E_c,
                    "E_d_static_base": E_d, "total_error_d_minus_a": total,
                    "temporal_component": temporal, "spatial_component": spatial, "trajectory_component": trajectory,
                    "temporal_pct_of_total": 100 * temporal / total if total else np.nan,
                    "spatial_pct_of_total": 100 * spatial / total if total else np.nan,
                    "trajectory_pct_of_total": 100 * trajectory / total if total else np.nan,
                    "total_error_pct_of_Ea": 100 * total / E_a if E_a else np.nan,
                    "pct_breakdown_unstable": abs(100 * total / E_a) < 5 if E_a else True,
                })

decomp = pd.DataFrame(decomp_rows)
decomp.to_csv(TABLES / "real_shape_decomposition_full.csv", index=False)
log(f"\nWrote real_shape_decomposition_full.csv ({len(decomp)} rows)")

log("\n=== Headline: Reference, NI, start=2027, all 6 real buildings and sample average, 10yr ===")
hl = decomp[(decomp["scenario"] == "Reference") & (decomp["start_year"] == HEADLINE_START) &
            (decomp["study_period_yrs_requested"] == 10)]
log(hl[["load_shape", "total_error_pct_of_Ea", "temporal_pct_of_total",
        "spatial_pct_of_total", "trajectory_pct_of_total"]].to_string(index=False))

with open(LOGS / "03_decomposition_real_shapes_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("\nDone.")
