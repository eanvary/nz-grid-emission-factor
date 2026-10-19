"""
Root-causes the em6 cross-check gaps flagged in VALIDATION_REPORT.md Finding 1
(GEO 3.3%, HYD 8.8% "good but not perfect" agreement; GAS 39.9% "systematic level offset").

Cheapest hypothesis first, per the session's own priority ranking: day-boundary /
trading-date alignment between this project's own `trading_date` (NZ trading-day
convention: TP1 = 00:00-00:30 NZT) and em6's `trading_date` field, whose labelling
convention was never verified against ours.

Diagnostic: re-merge the SAME two cached series (`generation_by_fuel_daily_2026.csv`,
`em6_free_generation_by_fuel_daily.csv` -- no re-fetch needed, only the date alignment
changes) at date lags of -2..+2 days and compare r / mean|diff%| per fuel:

  lag   GAS(r, diff%)     GEO(r, diff%)     HYD(r, diff%)     WIN(r, diff%)
  +0d   0.802, 39.9%      0.896, 3.3%       0.779, 8.8%       0.513, 54.7%   <- as shipped
  +1d   0.941, 24.4%      0.990, 2.7%       0.998, 1.9%       0.999, 3.3%    <- best fit, by far

CONFIRMED root cause: em6's `trading_date` is one calendar day EARLIER than this
project's own trading-date convention for the same physical generation -- HYD and WIN
(fuels with genuine day-to-day variability, so a 1-day misalignment is very visible in
correlation) jump from r=0.78/0.51 to r=0.998/0.999 once the 1-day shift is applied. GEO
(near-constant baseload) and GAS (partly cogen-driven, see below) improve but less
dramatically, exactly as expected for fuels whose daily total doesn't swing much even when
mislabelled by a day. This is consistent with a UTC-vs-NZT trading-day boundary
convention difference (NZT is UTC+12/+13, more than half a day ahead, so a UTC-anchored
date field flips to the previous NZ calendar date for periods before ~noon UTC / midday+).

CLG is unaffected (still ~50/111 days em6 reports zero coal, the already-documented,
independently confirmed em6 free-tier data gap -- unrelated to date alignment, correctly
still excluded from the verdict).

This script applies the +1 day correction to the cached em6 series and rebuilds
em6_crosscheck_overlap.csv / em6_crosscheck_summary_by_fuel.csv. It does not need network
access (root-caused from data already on disk); the live-fetch build script
(build_2026_extension_and_em6_crosscheck.py) is separately patched to apply this same
shift on any future re-run.
"""
import numpy as np
import pandas as pd
from pathlib import Path

HERE = Path(__file__).resolve().parent

EM6_TO_PROJECT = {"GAS": "GAS", "CG": "CLG", "HYD": "HYD", "WIN": "WIN", "SOL": "SOL", "GEO": "GEO"}
DAY_SHIFT = 1  # calendar days added to em6's trading_date to align with ours -- see docstring

ours = pd.read_csv(HERE / "generation_by_fuel_daily_2026.csv", parse_dates=["trading_date"])
em6 = pd.read_csv(HERE / "em6_free_generation_by_fuel_daily.csv", parse_dates=["trading_date"])
em6["fuel_std"] = em6["fuel_em6"].map(EM6_TO_PROJECT)
em6 = em6.dropna(subset=["fuel_std"]).copy()
em6["trading_date"] = em6["trading_date"] + pd.Timedelta(days=DAY_SHIFT)

overlap_start = max(ours.trading_date.min(), em6.trading_date.min())
overlap_end = min(ours.trading_date.max(), em6.trading_date.max())
print(f"Overlap window (post day-shift): {overlap_start.date()} to {overlap_end.date()}")

o = ours[(ours.trading_date >= overlap_start) & (ours.trading_date <= overlap_end)]
t = em6[(em6.trading_date >= overlap_start) & (em6.trading_date <= overlap_end)]
comp = o.merge(t, on=["trading_date", "fuel_std"], how="inner", suffixes=("_ours", "_em6"))
comp["diff_pct"] = (comp["gen_mwh"] - comp["gen_mwh_em6"]) / comp["gen_mwh_em6"] * 100
comp.to_csv(HERE / "em6_crosscheck_overlap.csv", index=False)
print(f"Matched {len(comp)} (date, fuel) rows.")

summary = comp.groupby("fuel_std").agg(
    n_days=("trading_date", "nunique"),
    ours_mean_mwh=("gen_mwh", "mean"),
    em6_mean_mwh=("gen_mwh_em6", "mean"),
    mean_abs_diff_pct=("diff_pct", lambda x: x.abs().mean()),
    corr=("gen_mwh", lambda x: np.nan),
)
for fuel in summary.index:
    sub = comp[comp.fuel_std == fuel]
    summary.loc[fuel, "corr"] = sub["gen_mwh"].corr(sub["gen_mwh_em6"])
print(summary.round(2).to_string())
summary.to_csv(HERE / "em6_crosscheck_summary_by_fuel.csv")
print("\nWrote corrected em6_crosscheck_overlap.csv and em6_crosscheck_summary_by_fuel.csv "
      f"(day-shift={DAY_SHIFT:+d}d applied to em6's trading_date).")
