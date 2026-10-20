import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGS = ROOT / "output" / "edgs"
HIST = ROOT / "output"
TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

hist = pd.read_csv(HIST / "hourly_emission_factor_NI_SI.csv")
hist["datetime_hour"] = pd.to_datetime(hist["date"]) + pd.to_timedelta(hist["hour"], unit="h")
hist["ef_kg_per_kwh"] = hist["EF_kg_per_MWh"] / 1000.0
hist_overlap = hist[hist["datetime_hour"].dt.year.isin([2024, 2025])][["island", "datetime_hour", "ef_kg_per_kwh", "total_gen_MWh"]].copy()
hist_overlap = hist_overlap.rename(columns={"ef_kg_per_kwh": "hist_ef", "total_gen_MWh": "hist_gen_mwh"})
log(f"Historical 2024-2025 overlap rows: {len(hist_overlap)}")

proj = pd.read_parquet(EDGS / "edgs_hourly_emission_factor.parquet")
proj = proj[(proj["scenario"] == "Reference") & (proj["ef_basis"] == "generation") &
            (proj["island"].isin(["NI", "SI"])) &
            (proj["datetime_hour"].dt.year.isin([2024, 2025]))]
proj = proj[["island", "datetime_hour", "emission_factor_kg_co2e_per_kwh"]].rename(
    columns={"emission_factor_kg_co2e_per_kwh": "proj_ef"})
log(f"Projected Reference 2024-2025 rows: {len(proj)}")

merged = hist_overlap.merge(proj, on=["island", "datetime_hour"], how="inner")
log(f"Matched rows: {len(merged)}")

merged["diff"] = merged["proj_ef"] - merged["hist_ef"]
merged["abs_pct_diff"] = 100 * merged["diff"].abs() / merged["hist_ef"].replace(0, np.nan)

log("\n--- Annual mean EF: historical (metered) and projected (Reference, generation-side) ---")
for isl in ["NI", "SI"]:
    for yr in [2024, 2025]:
        sub = merged[(merged["island"] == isl) & (merged["datetime_hour"].dt.year == yr)]
        h_mean = (sub["hist_ef"] * sub["hist_gen_mwh"]).sum() / sub["hist_gen_mwh"].sum()
        p_mean = sub["proj_ef"].mean()  # simple hourly mean, not gen-weighted
        p_mean_w = None
        log(f"  {isl} {yr}: hist gen-weighted mean EF = {h_mean:.5f} kg/kWh | "
            f"proj simple mean EF = {p_mean:.5f} kg/kWh | diff = {100*(p_mean-h_mean)/h_mean:.2f}%")

log("\n--- Shape fidelity: correlation of hourly EF (projected against historical), by island-year ---")
for isl in ["NI", "SI"]:
    for yr in [2024, 2025]:
        sub = merged[(merged["island"] == isl) & (merged["datetime_hour"].dt.year == yr)]
        corr = sub["hist_ef"].corr(sub["proj_ef"])
        log(f"  {isl} {yr}: hourly EF correlation (Pearson) = {corr:.4f}, n={len(sub)}")

log("\n--- Diurnal profile fidelity: correlation of hour-of-day mean EF ---")
merged["hod"] = merged["datetime_hour"].dt.hour
for isl in ["NI", "SI"]:
    for yr in [2024, 2025]:
        sub = merged[(merged["island"] == isl) & (merged["datetime_hour"].dt.year == yr)]
        prof = sub.groupby("hod")[["hist_ef", "proj_ef"]].mean()
        corr = prof["hist_ef"].corr(prof["proj_ef"])
        log(f"  {isl} {yr}: diurnal-profile correlation (24 hour-of-day means) = {corr:.4f}")

log("\n--- Overall abs_pct_diff distribution (hourly level) ---")
log(merged["abs_pct_diff"].describe().to_string())

merged.to_csv(TABLES / "phase0_hist_vs_proj_overlap.csv", index=False)
with open(LOGS / "phase0_hist_overlap_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log(f"\nWrote outputs.")
