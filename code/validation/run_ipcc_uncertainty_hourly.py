"""
Closes VALIDATION_REPORT.md Finding 4 ("the shipped hourly table cannot support a
genuinely hourly uncertainty band"): re-runs the same IPCC Approach-1 propagation as
run_ipcc_uncertainty_quantification.py, but against the newly-built
hourly_fuel_mix_NI_SI.csv (built by build_hourly_fuel_mix.py, verified to reconcile
exactly to the shipped pipeline output) instead of the monthly fuel-mix table.

Same method, same IPCC Table 2.2 fuel bounds, same GEO/ELE exclusion -- only the input
resolution changes, so any difference between this script's output and the monthly
script's output is a genuine resolution effect, not a methodology change.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SRC = HERE / "hourly_fuel_mix_NI_SI.csv"
OUT_HOURLY = HERE / "ipcc_uncertainty_by_island_hour.csv"
OUT_DAILY = HERE / "ipcc_uncertainty_by_island_day.csv"
OUT_YEAR = HERE / "ipcc_uncertainty_by_island_year_from_hourly.csv"

# Identical to run_ipcc_uncertainty_quantification.py -- IPCC 2006 GL Vol 2 Ch 2 Table 2.2
IPCC_TABLE_2_2 = {
    "CLG": (96100.0, 92800.0, 100000.0),
    "GAS": (56100.0, 54300.0, 58300.0),
    "DSL": (74100.0, 72600.0, 74800.0),
    "WOOD": (112000.0, 95000.0, 132000.0),
}
ZERO_EF_FUELS = {"HYD", "WIN", "SOL"}
EXCLUDED_FUELS = {"GEO", "ELE"}


def rel_half_width(default, lower, upper):
    return (abs(default - lower) / default + abs(upper - default) / default) / 2.0


REL_SIGMA = {f: rel_half_width(*v) for f, v in IPCC_TABLE_2_2.items()}

print("Loading hourly per-fuel table...")
df = pd.read_csv(SRC)
df["date"] = pd.to_datetime(df["date"])


def propagate_group(g):
    total_gen = g["gen_mwh"].sum()
    if total_gen <= 0:
        return pd.Series({"point_ef_kg_per_mwh": 0.0, "sigma_kg_per_mwh": 0.0,
                           "quantified_coverage_pct": 0.0, "excluded_coverage_pct": 0.0,
                           "total_gen_mwh": 0.0})
    point_ef = (g["gen_mwh"] * g["ef_kg_per_mwh"]).sum() / total_gen
    var = 0.0
    quantified_gen = 0.0
    excluded_gen = 0.0
    for _, row in g.iterrows():
        code = row["fuel_std"]
        w = row["gen_mwh"] / total_gen
        if code in ZERO_EF_FUELS:
            quantified_gen += row["gen_mwh"]
            continue
        if code in EXCLUDED_FUELS or code not in REL_SIGMA:
            excluded_gen += row["gen_mwh"]
            continue
        sigma_i = row["ef_kg_per_mwh"] * REL_SIGMA[code]
        var += (w * sigma_i) ** 2
        quantified_gen += row["gen_mwh"]
    sigma = math.sqrt(var)
    return pd.Series({
        "point_ef_kg_per_mwh": point_ef,
        "sigma_kg_per_mwh": sigma,
        "quantified_coverage_pct": quantified_gen / total_gen * 100.0,
        "excluded_coverage_pct": excluded_gen / total_gen * 100.0,
        "total_gen_mwh": total_gen,
    })


# --- vectorised version of the same logic (the row-iterrows version above is the
# reference/readable form; for 192,864 groups iterrows is too slow, so the actual
# computation below is a vectorised equivalent, cross-checked against propagate_group
# on a random sample before trusting it at scale). ---
df["rel_sigma"] = df["fuel_std"].map(REL_SIGMA).fillna(0.0)
df["is_quantified_combustion"] = df["fuel_std"].isin(REL_SIGMA.keys())
df["is_zero_ef"] = df["fuel_std"].isin(ZERO_EF_FUELS)
df["is_excluded"] = ~(df["is_quantified_combustion"] | df["is_zero_ef"])
df["sigma_i"] = df["ef_kg_per_mwh"] * df["rel_sigma"]

grp = df.groupby(["island", "date", "hour"], sort=False)
total_gen = grp["gen_mwh"].sum()
weighted_co2 = (df["gen_mwh"] * df["ef_kg_per_mwh"]).groupby([df["island"], df["date"], df["hour"]]).sum()
point_ef = weighted_co2 / total_gen

# variance contribution only from combustion-quantified rows
df_q = df[df["is_quantified_combustion"]].copy()
df_q["w_sigma_sq"] = 0.0  # filled below per-row using total_gen via merge
tg = total_gen.rename("total_gen_mwh").reset_index()
df_q = df_q.merge(tg, on=["island", "date", "hour"], how="left")
df_q["w"] = df_q["gen_mwh"] / df_q["total_gen_mwh"]
df_q["contrib"] = (df_q["w"] * df_q["sigma_i"]) ** 2
var_by_group = df_q.groupby(["island", "date", "hour"], sort=False)["contrib"].sum()

quantified_gen = df[df["is_quantified_combustion"] | df["is_zero_ef"]].groupby(
    ["island", "date", "hour"], sort=False
)["gen_mwh"].sum()
excluded_gen = df[df["is_excluded"]].groupby(["island", "date", "hour"], sort=False)["gen_mwh"].sum()

result = pd.DataFrame({"total_gen_mwh": total_gen, "point_ef_kg_per_mwh": point_ef})
result["sigma_kg_per_mwh"] = var_by_group.reindex(result.index).fillna(0.0).apply(math.sqrt)
result["quantified_coverage_pct"] = (quantified_gen.reindex(result.index).fillna(0.0) / result["total_gen_mwh"] * 100.0)
result["excluded_coverage_pct"] = (excluded_gen.reindex(result.index).fillna(0.0) / result["total_gen_mwh"] * 100.0)
result = result.reset_index()

# --- cross-check the vectorised path against the reference row-wise function on a
# random sample of 200 (island,date,hour) groups before trusting it further. ---
print("Cross-checking vectorised computation against the reference row-wise function...")
sample_keys = result.sample(n=min(200, len(result)), random_state=0)[["island", "date", "hour"]]
max_ef_diff, max_sigma_diff = 0.0, 0.0
for _, k in sample_keys.iterrows():
    g = df[(df["island"] == k["island"]) & (df["date"] == k["date"]) & (df["hour"] == k["hour"])]
    ref = propagate_group(g)
    row = result[(result["island"] == k["island"]) & (result["date"] == k["date"]) & (result["hour"] == k["hour"])].iloc[0]
    max_ef_diff = max(max_ef_diff, abs(ref["point_ef_kg_per_mwh"] - row["point_ef_kg_per_mwh"]))
    max_sigma_diff = max(max_sigma_diff, abs(ref["sigma_kg_per_mwh"] - row["sigma_kg_per_mwh"]))
print(f"  max |EF diff| over 200-sample cross-check: {max_ef_diff:.10f}")
print(f"  max |sigma diff| over 200-sample cross-check: {max_sigma_diff:.10f}")
assert max_ef_diff < 1e-8 and max_sigma_diff < 1e-8, "vectorised path does not match reference logic"
print("  PASS -- vectorised and reference computations agree.")

result["ci95_lower_kg_per_mwh"] = result["point_ef_kg_per_mwh"] - 1.96 * result["sigma_kg_per_mwh"]
result["ci95_upper_kg_per_mwh"] = result["point_ef_kg_per_mwh"] + 1.96 * result["sigma_kg_per_mwh"]
result["ci95_pct_of_point"] = np.where(
    result["point_ef_kg_per_mwh"] > 0,
    1.96 * result["sigma_kg_per_mwh"] / result["point_ef_kg_per_mwh"] * 100.0,
    np.nan,
)
result.to_csv(OUT_HOURLY, index=False)
print(f"\nWrote {len(result):,} island-hour rows -> {OUT_HOURLY}")

# Daily roll-up (energy-weighted point EF, variance combined assuming hour-independence
# -- same disclosed simplification as the monthly->annual roll-up already in the report)
result["year"] = pd.to_datetime(result["date"]).dt.year
daily = result.groupby(["island", "date"]).apply(
    lambda g: pd.Series({
        "point_ef_kg_per_mwh": (g["point_ef_kg_per_mwh"] * g["total_gen_mwh"]).sum() / g["total_gen_mwh"].sum(),
        "sigma_kg_per_mwh": math.sqrt(((g["sigma_kg_per_mwh"] * g["total_gen_mwh"] / g["total_gen_mwh"].sum()) ** 2).sum()),
        "quantified_coverage_pct": (g["quantified_coverage_pct"] * g["total_gen_mwh"]).sum() / g["total_gen_mwh"].sum(),
        "total_gen_mwh": g["total_gen_mwh"].sum(),
    }),
    include_groups=False,
).reset_index()
daily["ci95_pct_of_point"] = 1.96 * daily["sigma_kg_per_mwh"] / daily["point_ef_kg_per_mwh"] * 100.0
daily.to_csv(OUT_DAILY, index=False)
print(f"Wrote {len(daily):,} island-day rows -> {OUT_DAILY}")

# Annual roll-up from hourly (compare directly against the monthly-derived annual file)
result["year"] = pd.to_datetime(result["date"]).dt.year
annual = result.groupby(["island", "year"]).apply(
    lambda g: pd.Series({
        "point_ef_kg_per_mwh": (g["point_ef_kg_per_mwh"] * g["total_gen_mwh"]).sum() / g["total_gen_mwh"].sum(),
        "sigma_kg_per_mwh": math.sqrt(((g["sigma_kg_per_mwh"] * g["total_gen_mwh"] / g["total_gen_mwh"].sum()) ** 2).sum()),
        "quantified_coverage_pct": (g["quantified_coverage_pct"] * g["total_gen_mwh"]).sum() / g["total_gen_mwh"].sum(),
        "total_gen_mwh": g["total_gen_mwh"].sum(),
    }),
    include_groups=False,
).reset_index()
annual["ci95_pct_of_point"] = 1.96 * annual["sigma_kg_per_mwh"] / annual["point_ef_kg_per_mwh"] * 100.0
annual.to_csv(OUT_YEAR, index=False)
print(f"Wrote {len(annual):,} island-year rows (from hourly) -> {OUT_YEAR}")

ni_hourly = result[(result["island"] == "NI") & (result["point_ef_kg_per_mwh"] > 0)]
ni_daily = daily[(daily["island"] == "NI") & (daily["point_ef_kg_per_mwh"] > 0)]
ni_annual_h = annual[annual["island"] == "NI"]
print("\n=== Summary: NI, hourly-native uncertainty vs. the monthly-derived figures already in the report ===")
print(f"Hourly CI%: min={ni_hourly['ci95_pct_of_point'].min():.2f}% "
      f"max={ni_hourly['ci95_pct_of_point'].max():.2f}% mean={ni_hourly['ci95_pct_of_point'].mean():.2f}%  (n={len(ni_hourly):,} hours)")
print(f"Daily CI%:  min={ni_daily['ci95_pct_of_point'].min():.2f}% "
      f"max={ni_daily['ci95_pct_of_point'].max():.2f}% mean={ni_daily['ci95_pct_of_point'].mean():.2f}%  (n={len(ni_daily):,} days)")
print(f"Annual CI% (from hourly): min={ni_annual_h['ci95_pct_of_point'].min():.2f}% "
      f"max={ni_annual_h['ci95_pct_of_point'].max():.2f}%  (n={len(ni_annual_h)} years)")
print(f"Annual coverage % (from hourly): min={ni_annual_h['quantified_coverage_pct'].min():.1f}% "
      f"max={ni_annual_h['quantified_coverage_pct'].max():.1f}%")
