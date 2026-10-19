"""
Phase 1, item 5: within-year structure.
Diurnal profiles, weekday/weekend contrast, seasonal patterns, and their
evolution across the projection horizon; duration curves; zero-thermal-hour
and high-EF-tail-hour counts over time.
Generation-side EF, NI and SI, all 5 scenarios. Representative years
2024, 2030, 2035, 2040, 2050 used for shape comparisons to keep output tractable;
duration-curve percentiles and tail-hour counts computed for every year.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGS = ROOT / "output" / "edgs"
TABLES = Path(__file__).resolve().parents[1] / "tables"
FIGS = Path(__file__).resolve().parents[1] / "figures"
LOGS = Path(__file__).resolve().parents[1] / "logs"

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

ef = pd.read_parquet(EDGS / "edgs_hourly_emission_factor.parquet")
ef = ef[(ef["ef_basis"] == "generation") & (ef["island"].isin(["NI", "SI"]))].copy()
ef["year"] = ef["datetime_hour"].dt.year
ef["hour"] = ef["datetime_hour"].dt.hour
ef["dow"] = ef["datetime_hour"].dt.dayofweek  # 0=Mon
ef["is_weekend"] = ef["dow"] >= 5
ef["month"] = ef["datetime_hour"].dt.month
def season(m):
    return {12: "Summer", 1: "Summer", 2: "Summer", 3: "Autumn", 4: "Autumn", 5: "Autumn",
            6: "Winter", 7: "Winter", 8: "Winter", 9: "Spring", 10: "Spring", 11: "Spring"}[m]
ef["season"] = ef["month"].map(season)
log(f"Loaded {len(ef)} generation-side NI/SI hourly EF rows")

REP_YEARS = [2024, 2030, 2035, 2040, 2045, 2050]

# --- Diurnal profiles, representative years, all scenarios ---
diurnal = (ef[ef["year"].isin(REP_YEARS)]
           .groupby(["scenario", "island", "year", "hour"])["emission_factor_kg_co2e_per_kwh"]
           .mean().reset_index())
diurnal.to_csv(TABLES / "phase1_diurnal_profiles.csv", index=False)
log(f"Wrote phase1_diurnal_profiles.csv ({len(diurnal)} rows)")

# Diurnal shape persistence: correlation of each rep year's 24-hour profile
# against the 2024 profile, per scenario x island -- flattens toward 0 as
# solar/batteries reshape the day; inverts if correlation goes negative.
log("\n=== Diurnal-shape persistence: corr(hour-of-day profile in year Y, profile in 2024) ===")
persist_rows = []
for (scen, isl), g in diurnal.groupby(["scenario", "island"]):
    base = g[g["year"] == 2024].set_index("hour")["emission_factor_kg_co2e_per_kwh"]
    for yr in REP_YEARS:
        cur = g[g["year"] == yr].set_index("hour")["emission_factor_kg_co2e_per_kwh"]
        corr = base.corr(cur)
        persist_rows.append({"scenario": scen, "island": isl, "year": yr, "corr_vs_2024": corr})
persist_df = pd.DataFrame(persist_rows)
log(persist_df.pivot_table(index=["island", "scenario"], columns="year", values="corr_vs_2024").round(3).to_string())
persist_df.to_csv(TABLES / "phase1_diurnal_shape_persistence.csv", index=False)

# --- Peak-hour identification: which hour-of-day has max/min EF, by year ---
log("\n=== Hour-of-day with max and min mean EF, by year (Reference scenario) ===")
ref_diurnal = diurnal[diurnal["scenario"] == "Reference"]
for isl in ["NI", "SI"]:
    for yr in REP_YEARS:
        g = ref_diurnal[(ref_diurnal["island"] == isl) & (ref_diurnal["year"] == yr)]
        if g["emission_factor_kg_co2e_per_kwh"].isna().all():
            continue
        hmax = g.loc[g["emission_factor_kg_co2e_per_kwh"].idxmax()]
        hmin = g.loc[g["emission_factor_kg_co2e_per_kwh"].idxmin()]
        log(f"  {isl} {yr}: max EF at hour {int(hmax['hour']):02d}:00 ({hmax['emission_factor_kg_co2e_per_kwh']:.4f}), "
            f"min EF at hour {int(hmin['hour']):02d}:00 ({hmin['emission_factor_kg_co2e_per_kwh']:.4f})")

# --- Weekday/weekend contrast, by year ---
wkdwknd = (ef.groupby(["scenario", "island", "year", "is_weekend"])["emission_factor_kg_co2e_per_kwh"]
           .mean().reset_index())
wkdwknd_p = wkdwknd.pivot_table(index=["scenario", "island", "year"], columns="is_weekend",
                                 values="emission_factor_kg_co2e_per_kwh").reset_index()
wkdwknd_p.columns = ["scenario", "island", "year", "weekday_mean_ef", "weekend_mean_ef"]
wkdwknd_p["weekend_minus_weekday_pct"] = 100 * (wkdwknd_p["weekend_mean_ef"] - wkdwknd_p["weekday_mean_ef"]) / wkdwknd_p["weekday_mean_ef"]
wkdwknd_p.to_csv(TABLES / "phase1_weekday_weekend.csv", index=False)
log("\n=== Weekday vs weekend EF, Reference scenario, rep years ===")
log(wkdwknd_p[(wkdwknd_p["scenario"] == "Reference") & (wkdwknd_p["year"].isin(REP_YEARS))].to_string(index=False))

# --- Seasonal pattern, by year ---
seasonal = (ef.groupby(["scenario", "island", "year", "season"])["emission_factor_kg_co2e_per_kwh"]
            .mean().reset_index())
seasonal.to_csv(TABLES / "phase1_seasonal.csv", index=False)
log("\n=== Seasonal mean EF, Reference scenario, rep years ===")
log(seasonal[(seasonal["scenario"] == "Reference") & (seasonal["year"].isin(REP_YEARS))]
    .pivot_table(index=["island", "year"], columns="season", values="emission_factor_kg_co2e_per_kwh").to_string())

# --- Duration curves: percentiles of hourly EF, every year, all scenarios ---
log("\n=== Duration-curve percentiles (all years) -> phase1_duration_curve_percentiles.csv ===")
pctiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
dur = (ef.groupby(["scenario", "island", "year"])["emission_factor_kg_co2e_per_kwh"]
       .quantile([p / 100 for p in pctiles]).unstack())
dur.columns = [f"p{p}" for p in pctiles]
dur = dur.reset_index()
dur.to_csv(TABLES / "phase1_duration_curve_percentiles.csv", index=False)
log(f"Wrote phase1_duration_curve_percentiles.csv ({len(dur)} rows)")

# --- Zero-thermal / near-zero hours and high-EF tail hours, count per year ---
# Data-driven thresholds: "near-zero" = below the 5th percentile of that
# scenario-island's OWN 2024 distribution (so the bar migrates with the fleet,
# not a fixed round number); "high-EF tail" = above the 95th percentile of that
# scenario-island's own 2024 distribution.
log("\n=== Zero/near-zero-EF and high-EF-tail hour counts per year (thresholds = own-2024 p5/p95) ===")
tail_rows = []
for (scen, isl), g in ef.groupby(["scenario", "island"]):
    base = g[g["year"] == 2024]["emission_factor_kg_co2e_per_kwh"]
    p5_2024, p95_2024 = base.quantile(0.05), base.quantile(0.95)
    literal_zero_2024 = (base <= 1e-9).sum()
    for yr, gy in g.groupby("year"):
        n_near_zero = (gy["emission_factor_kg_co2e_per_kwh"] <= p5_2024).sum()
        n_literal_zero = (gy["emission_factor_kg_co2e_per_kwh"] <= 1e-9).sum()
        n_high_tail = (gy["emission_factor_kg_co2e_per_kwh"] >= p95_2024).sum()
        tail_rows.append({"scenario": scen, "island": isl, "year": yr,
                           "n_hours_le_2024_p5": n_near_zero, "n_hours_literal_zero": n_literal_zero,
                           "n_hours_ge_2024_p95": n_high_tail})
tail_df = pd.DataFrame(tail_rows)
tail_df.to_csv(TABLES / "phase1_tail_hour_counts.csv", index=False)
log(tail_df[tail_df["scenario"] == "Reference"].pivot_table(
    index="year", columns="island", values=["n_hours_literal_zero", "n_hours_ge_2024_p95"]).to_string())

with open(LOGS / "phase1_within_year_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("\nDone.")
