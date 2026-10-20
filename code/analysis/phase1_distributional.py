"""
Phase 1: distributional characterisation.
Skewness, kurtosis, tail ratios, and intermittency (CV) of hourly EF, and a
formal test of whether the annual mean becomes an increasingly poor summary
statistic over the projection horizon (mean-median divergence, CV trend).
Generation-side, NI only (SI is degenerate/near-zero throughout, see Phase 0/1).
"""
import numpy as np
import pandas as pd
from scipy import stats
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGS = ROOT / "output" / "edgs"
TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

ef = pd.read_parquet(EDGS / "edgs_hourly_emission_factor.parquet")
ef = ef[(ef["ef_basis"] == "generation") & (ef["island"] == "NI")].copy()
ef["year"] = ef["datetime_hour"].dt.year
log(f"Loaded {len(ef)} NI generation-side rows")

rows = []
for (scen, yr), g in ef.groupby(["scenario", "year"]):
    v = g["emission_factor_kg_co2e_per_kwh"]
    mean, median, std = v.mean(), v.median(), v.std()
    rows.append({
        "scenario": scen, "year": yr,
        "mean": mean, "median": median, "std": std,
        "cv": std / mean if mean else np.nan,
        "skewness": stats.skew(v), "kurtosis_excess": stats.kurtosis(v),
        "p99_over_median": v.quantile(0.99) / median if median else np.nan,
        "p95_over_median": v.quantile(0.95) / median if median else np.nan,
        "mean_minus_median_pct": 100 * (mean - median) / mean if mean else np.nan,
        "frac_hours_zero": float((v <= 1e-9).mean()),
    })
dist = pd.DataFrame(rows)
dist.to_csv(TABLES / "phase1_distributional_stats.csv", index=False)
log(f"Wrote phase1_distributional_stats.csv ({len(dist)} rows)")

log("\n=== Reference scenario, NI: distributional stats over time ===")
log(dist[dist["scenario"] == "Reference"][
    ["year", "mean", "median", "cv", "skewness", "kurtosis_excess", "p99_over_median",
     "mean_minus_median_pct", "frac_hours_zero"]].to_string(index=False))

log("\n=== Formal trend tests: do the mean-median divergence and CV grow over 2024-2050? ===")
for scen, g in dist.groupby("scenario"):
    g = g.sort_values("year")
    slope_cv, _, r_cv, p_cv, _ = stats.linregress(g["year"], g["cv"])
    slope_mm, _, r_mm, p_mm, _ = stats.linregress(g["year"], g["mean_minus_median_pct"])
    slope_zero, _, r_zero, p_zero, _ = stats.linregress(g["year"], g["frac_hours_zero"])
    log(f"  {scen}: CV trend slope={slope_cv:+.5f}/yr (r={r_cv:.3f}, p={p_cv:.4f}) | "
        f"mean-median-gap%% trend slope={slope_mm:+.4f}/yr (r={r_mm:.3f}, p={p_mm:.4f}) | "
        f"frac-zero-hours trend slope={slope_zero:+.5f}/yr (r={r_zero:.3f}, p={p_zero:.4f})")

with open(LOGS / "phase1_distributional_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("\nDone.")
