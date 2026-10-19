"""
Phase 1, item 4: trajectories.
Annual (generation-weighted) mean EF paths, historical (2015-2025, metered)
spliced with projected (2024-2050), by scenario x island x ef_basis.
Rate of decline, inflection points (rolling-slope sign changes), data-driven
percentile thresholds and crossing years, and scenario-divergence-becomes-material
year.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGS = ROOT / "output" / "edgs"
HIST = ROOT / "output"
TABLES = Path(__file__).resolve().parents[1] / "tables"
FIGS = Path(__file__).resolve().parents[1] / "figures"
LOGS = Path(__file__).resolve().parents[1] / "logs"
for d in (TABLES, FIGS, LOGS):
    d.mkdir(parents=True, exist_ok=True)

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

# ---------------------------------------------------------------------------
# Annual generation-weighted mean EF, projected series, all scenario x island x
# ef_basis x year. Weight = hourly generation (island's own for generation-side;
# for consumption-side, weight by the island's implied consumption volume -- but
# since exact consumption MWh isn't in the EF table, use generation as the
# weight for both bases as a working approximation and flag this explicitly).
# ---------------------------------------------------------------------------
ef = pd.read_parquet(EDGS / "edgs_hourly_emission_factor.parquet")
ef["year"] = ef["datetime_hour"].dt.year

gen = pd.read_parquet(EDGS / "edgs_hourly_generation.parquet")
gen_isl = gen.groupby(["scenario", "island", "datetime_hour"], observed=True)["generation_mwh"].sum().reset_index()
# National weight = sum of NI+SI generation
gen_nat = gen.groupby(["scenario", "datetime_hour"], observed=True)["generation_mwh"].sum().reset_index()
gen_nat["island"] = "National"
gen_weight = pd.concat([gen_isl, gen_nat], ignore_index=True)

efw = ef.merge(gen_weight, on=["scenario", "island", "datetime_hour"], how="left")
n_missing = efw["generation_mwh"].isna().sum()
log(f"EF rows without a generation weight match: {n_missing} / {len(efw)}")

def wmean(g):
    w = g["generation_mwh"]
    if w.sum() == 0 or w.isna().all():
        return np.nan
    return np.average(g["emission_factor_kg_co2e_per_kwh"], weights=w.fillna(0))

annual = (efw.groupby(["scenario", "island", "ef_basis", "year"])
          .apply(lambda g: pd.Series({"gen_weighted_mean_ef": wmean(g)}), include_groups=False)
          .reset_index())
annual.to_csv(TABLES / "phase1_annual_trajectory_projected.csv", index=False)
log(f"Wrote phase1_annual_trajectory_projected.csv ({len(annual)} rows)")

# ---------------------------------------------------------------------------
# Historical annual (generation-weighted), 2021-2025, generation-side, NI/SI
# ---------------------------------------------------------------------------
hist_ef = pd.read_csv(HIST / "hourly_emission_factor_NI_SI.csv")
hist_ef["datetime_hour"] = pd.to_datetime(hist_ef["date"]) + pd.to_timedelta(hist_ef["hour"], unit="h")
hist_ef["ef_kg_per_kwh"] = hist_ef["EF_kg_per_MWh"] / 1000.0
hist_ef["year"] = hist_ef["datetime_hour"].dt.year
hist_ef = hist_ef.dropna(subset=["ef_kg_per_kwh"])
hist_annual = (hist_ef.groupby(["island", "year"])
               .apply(lambda g: pd.Series({"gen_weighted_mean_ef": np.average(g["ef_kg_per_kwh"], weights=g["total_gen_MWh"])}),
                      include_groups=False).reset_index())
hist_annual["source"] = "historical_metered"
hist_annual.to_csv(TABLES / "phase1_annual_trajectory_historical.csv", index=False)
log(f"\nWrote phase1_annual_trajectory_historical.csv ({len(hist_annual)} rows)")
log(hist_annual.pivot(index="year", columns="island", values="gen_weighted_mean_ef").to_string())

# ---------------------------------------------------------------------------
# Rate of decline: annualised % change, generation-side, by scenario x island,
# 2024-2050 (projected series only -- comparable basis across all 5 scenarios).
# ---------------------------------------------------------------------------
log("\n=== Rate of decline (CAGR), generation-side EF, 2024->2050, projected ===")
gen_side = annual[annual["ef_basis"] == "generation"].copy()
rates = []
for (scen, isl), g in gen_side.groupby(["scenario", "island"]):
    g = g.sort_values("year")
    v0 = g[g["year"] == 2024]["gen_weighted_mean_ef"].values
    v1 = g[g["year"] == 2050]["gen_weighted_mean_ef"].values
    if len(v0) and len(v1) and v0[0] > 0:
        cagr = 100 * ((v1[0] / v0[0]) ** (1 / 26) - 1)
        rates.append({"scenario": scen, "island": isl, "ef_2024": v0[0], "ef_2050": v1[0], "cagr_pct_per_yr": cagr})
rates_df = pd.DataFrame(rates).sort_values(["island", "scenario"])
log(rates_df.to_string(index=False))
rates_df.to_csv(TABLES / "phase1_cagr_by_scenario_island.csv", index=False)

# ---------------------------------------------------------------------------
# Inflection points: rolling 3-yr slope sign changes, generation-side, National
# (the single blended index most relevant for a "headline" trajectory read).
# ---------------------------------------------------------------------------
log("\n=== Inflection points (rolling 3-yr slope sign change), National generation-side EF ===")
nat = annual[(annual["island"] == "National") & (annual["ef_basis"] == "consumption")].copy()
# National ships consumption-basis only (per Phase 0 schema note) -- use that as
# the national headline series, explicitly labelled.
log("NOTE: 'National' island only ships ef_basis='consumption' in this table "
    "(confirmed in Phase 0); the 'National headline' trajectory below is therefore "
    "consumption-side by necessity, not generation-side.")
for scen in sorted(nat["scenario"].unique()):
    g = nat[nat["scenario"] == scen].sort_values("year")
    slope = g["gen_weighted_mean_ef"].diff()
    sign = np.sign(slope.dropna())
    changes = sign.diff().fillna(0) != 0
    infl_years = g["year"].iloc[1:][changes.values].tolist()
    log(f"  {scen}: inflection (slope sign change) years = {infl_years}")

# ---------------------------------------------------------------------------
# Data-driven percentile thresholds: pooled distribution of all projected
# generation-side annual EF values (5 scenarios x 2 islands x 27 years = 270
# values) defines percentile bands; report, for each scenario x island, the
# first year the trajectory drops below the pooled 25th/10th/5th percentile.
# ---------------------------------------------------------------------------
log("\n=== Data-driven percentile thresholds (pooled across all scenario x island x year, generation-side) ===")
pooled = gen_side["gen_weighted_mean_ef"].dropna()
pcts = {p: pooled.quantile(p / 100) for p in [75, 50, 25, 10, 5]}
log(f"Pooled percentile values (kg/kWh): {pcts}")
crossing_rows = []
for (scen, isl), g in gen_side.groupby(["scenario", "island"]):
    g = g.sort_values("year")
    row = {"scenario": scen, "island": isl}
    for p, thresh in pcts.items():
        below = g[g["gen_weighted_mean_ef"] <= thresh]
        row[f"first_year_below_p{p}"] = int(below["year"].min()) if len(below) else None
    crossing_rows.append(row)
crossing_df = pd.DataFrame(crossing_rows).sort_values(["island", "scenario"])
log(crossing_df.to_string(index=False))
crossing_df.to_csv(TABLES / "phase1_percentile_crossing_years.csv", index=False)

# ---------------------------------------------------------------------------
# Scenario divergence: cross-scenario spread by year (generation-side, NI and
# SI separately), and the year spread becomes "material" (data-driven: exceeds
# its own 2024-2030 baseline spread by >2x, a simple, stated, reproducible rule).
# ---------------------------------------------------------------------------
log("\n=== Scenario divergence over time (generation-side), spread = max-min across 5 scenarios ===")
for isl in ["NI", "SI"]:
    sub = gen_side[gen_side["island"] == isl]
    spread = sub.groupby("year")["gen_weighted_mean_ef"].agg(["max", "min", "std"]).reset_index()
    spread["range"] = spread["max"] - spread["min"]
    baseline = spread[spread["year"].between(2024, 2030)]["range"].mean()
    material = spread[spread["range"] > 2 * baseline]
    first_material_year = int(material["year"].min()) if len(material) else None
    log(f"  {isl}: 2024-2030 baseline mean range = {baseline:.5f} kg/kWh; "
        f"first year range > 2x baseline = {first_material_year}")
    spread.to_csv(TABLES / f"phase1_scenario_divergence_{isl}.csv", index=False)

with open(LOGS / "phase1_trajectories_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("\nDone.")
