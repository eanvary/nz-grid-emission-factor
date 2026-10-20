"""
Phase 1: variance decomposition.
For each scenario-year, decompose total hourly-EF variance into shares
"explained" (eta-squared, marginal/between-group variance over total variance)
by hour-of-day, day-of-year (proxy: month, to keep groups populated), season,
and island. The decomposition is sequential and marginal, not orthogonalised.
Components are not guaranteed to sum to 100%, and they are order-independent by
construction: each factor's share is computed against the same total
variance, not residualised against the others. An ordered decomposition
would need its order sensitivity reported. Marginal shares avoid that
problem, at the cost of not summing to 100%. Any overlap between factors
shows up as double-counted variance. That overlap shows how confounded the
factors are, and it is reported alongside.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGS = ROOT / "output" / "edgs"
TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

ef = pd.read_parquet(EDGS / "edgs_hourly_emission_factor.parquet")
ef = ef[(ef["ef_basis"] == "generation") & (ef["island"].isin(["NI", "SI"]))].copy()
ef["year"] = ef["datetime_hour"].dt.year
ef["hour"] = ef["datetime_hour"].dt.hour
ef["month"] = ef["datetime_hour"].dt.month
def season(m):
    return {12: "Summer", 1: "Summer", 2: "Summer", 3: "Autumn", 4: "Autumn", 5: "Autumn",
            6: "Winter", 7: "Winter", 8: "Winter", 9: "Spring", 10: "Spring", 11: "Spring"}[m]
ef["season"] = ef["month"].map(season)
log(f"Loaded {len(ef)} rows")

def eta_sq(g, factor_col, value_col="emission_factor_kg_co2e_per_kwh"):
    total_var = g[value_col].var(ddof=0)
    if total_var == 0 or np.isnan(total_var):
        return np.nan
    group_means = g.groupby(factor_col)[value_col].transform("mean")
    between_var = ((group_means - g[value_col].mean()) ** 2).mean()
    return between_var / total_var

rows = []
for (scen, isl, yr), g in ef.groupby(["scenario", "island", "year"]):
    total_var = g["emission_factor_kg_co2e_per_kwh"].var(ddof=0)
    row = {"scenario": scen, "island": isl, "year": yr, "total_variance": total_var}
    for factor in ["hour", "month", "season"]:
        row[f"eta2_{factor}"] = eta_sq(g, factor)
    rows.append(row)
decomp = pd.DataFrame(rows)
decomp.to_csv(TABLES / "phase1_variance_decomp_by_island.csv", index=False)
log(f"Wrote phase1_variance_decomp_by_island.csv ({len(decomp)} rows)")

log("\n=== Reference scenario, NI: variance-share by factor, selected years ===")
log(decomp[(decomp["scenario"] == "Reference") & (decomp["island"] == "NI") &
           (decomp["year"].isin([2024, 2030, 2035, 2040, 2045, 2050]))]
    [["year", "total_variance", "eta2_hour", "eta2_month", "eta2_season"]].to_string(index=False))

# Between-island component: pool NI+SI together per scenario-year, compute
# eta2 for the island factor itself (this is where SI's near-zero EF creates
# a large, mechanical between-island variance share).
log("\n=== Between-island variance share (NI+SI pooled per scenario-year) ===")
isl_rows = []
for (scen, yr), g in ef.groupby(["scenario", "year"]):
    isl_rows.append({"scenario": scen, "year": yr, "eta2_island": eta_sq(g, "island")})
isl_df = pd.DataFrame(isl_rows)
isl_df.to_csv(TABLES / "phase1_variance_decomp_island_factor.csv", index=False)
log(isl_df[isl_df["scenario"] == "Reference"].to_string(index=False))

# Trend over horizon: does hour-of-day's share of variance grow or shrink as
# solar/batteries reshape the day? Linear trend (OLS slope) of eta2_hour
# against year, per scenario, NI only (SI's eta2 values are largely
# undefined or degenerate, since SI variance itself is about 0).
log("\n=== Trend in eta2_hour over 2024-2050, NI, per scenario (simple OLS slope) ===")
from scipy import stats
for scen, g in decomp[decomp["island"] == "NI"].groupby("scenario"):
    g = g.dropna(subset=["eta2_hour"]).sort_values("year")
    if len(g) < 3:
        continue
    slope, intercept, r, p, se = stats.linregress(g["year"], g["eta2_hour"])
    log(f"  {scen}: slope={slope:+.6f}/yr, r={r:.3f}, p={p:.4f}, "
        f"eta2_hour(2024)={g[g['year']==2024]['eta2_hour'].values}, "
        f"eta2_hour(2050)={g[g['year']==2050]['eta2_hour'].values}")

with open(LOGS / "phase1_variance_decomp_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("\nDone.")
