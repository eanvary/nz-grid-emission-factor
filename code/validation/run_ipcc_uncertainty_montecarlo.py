"""
Approach 2 (Monte Carlo) uncertainty propagation. Approach 1 (linear, first-order
error propagation, run_ipcc_uncertainty_full_coverage.py) implicitly assumes a symmetric,
unbounded Gaussian. Geothermal's very wide relative uncertainty (93.97%, McLean &
Richardson 2019) is included alongside GAS (adopted per-unit sigma,
build_fleet_uncertainty.py) and IPCC Table 2.2 defaults (CLG, DSL, WOOD). With these
inputs Approach 1 gives a negative lower 95% bound in 3,795 of 96,421 NI+SI hours
(3.9%), which is physically impossible for an emission factor.

Geothermal is split by proxy-rule step into independent terms
(build_geo_uncertainty_inputs.py): GEO, step 1, at the NIR 2026 measurement uncertainty
(Table 3.2.3, 7.07%); GEO_S2_<station>, step 2, at sqrt(7.07%^2 + the station's own
year-to-year variation^2); GEO_PROXY, steps 3-4, at the between-station spread (93.97%).

Method (IPCC Good Practice Guidance Ch.6, Approach 2): each quantified fuel's emission
factor is treated as one uncertain parameter, fixed for the study (not a fresh random
draw every hour). Its point estimate is the mean of a lognormal distribution whose
coefficient of variation equals that fuel's rel_sigma from Approach 1 (same inputs; only the
propagation method differs). The lognormal is strictly positive (support (0, inf)), which
removes Approach 1's negative-bound failure, and IPCC suggests it for emission factors that
cannot be negative.

For each of N Monte Carlo trials, one multiplier is drawn per fuel (E[mult]=1, CV=rel_sigma)
and applied identically to every hour of the whole 2015-2025 record before re-aggregating to
hourly, monthly and annual generation-weighted EF. The three resolutions thus share the same
trials and stay internally consistent. This is the correct treatment of a systematic parameter
uncertainty. Sampling independently every hour would average the uncertainty away and
understate it at monthly and annual resolution.

Zero-EF fuels (HYD, WIN, SOL) and the near-zero ELE column are held deterministic at their
point contribution (0), matching Approach 1's treatment.

Trial count (50,000)
Because one multiplier per fuel is held across the whole record, every hour shares the same
N draws. Monte Carlo error in the 2.5/97.5 percentiles is therefore common to all hours and
does not average away over the 96,421-hour record, which is the usual reason a modest N is
safe. Geothermal's 93.97% sigma also makes the lognormal tail heavy where those
percentiles sit. test_montecarlo_trial_convergence.py measures the effect: at N=10,000 the
mean band moves about 6 percentage points with the seed alone, at N=50,000 under 1.5, and at
N=200,000 under 0.5. 50,000 gives stability at the reported precision without the memory cost
of 200,000. CHUNK is 500 rows so the (chunk x N_TRIALS) working array stays near 200 MB.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
N_TRIALS = 50_000
CHUNK = 500
SEED = 42

# Rebuild REL_SIGMA_FULL exactly as in run_ipcc_uncertainty_full_coverage.py
IPCC_TABLE_2_2 = {
    "CLG": (96100.0, 92800.0, 100000.0), "GAS": (56100.0, 54300.0, 58300.0),
    "DSL": (74100.0, 72600.0, 74800.0), "WOOD": (112000.0, 95000.0, 132000.0),
}
def rel_half_width(d, lo, hi):
    return (abs(d - lo) / d + abs(hi - d) / d) / 2.0
REL_SIGMA = {f: rel_half_width(*v) for f, v in IPCC_TABLE_2_2.items()}

fleet = pd.read_csv(HERE / "fleet_uncertainty_by_fuel.csv").set_index("fuel_std")["rel_sigma_adopted"].to_dict()
REL_SIGMA["GAS"] = fleet["GAS"]

geo_df = pd.read_csv(HERE / "geothermal_mclean_richardson_stations.csv")
total_mw = geo_df.mw.sum()
geo_w_mean = (geo_df.mw * geo_df.ef_gco2_kwh).sum() / total_mw
geo_w_std = math.sqrt((geo_df.mw * (geo_df.ef_gco2_kwh - geo_w_mean) ** 2).sum() / total_mw)
# Geothermal by proxy-rule step, each term drawn independently: step 1 GEO (NIR 2026 Table
# 3.2.3, 7.07%); step 2 GEO_S2_<station> (7.07% with the station's own year-to-year variation); steps 3-4
# GEO_PROXY (between-station spread above, 93.97%). See build_geo_uncertainty_inputs.py.
_geo_sig = pd.read_csv(HERE / "geo_uncertainty_sigma.csv").set_index("fuel_std")["rel_sigma"]  # build_geo_uncertainty_inputs.py
REL_SIGMA.update({k: float(v) for k, v in _geo_sig.items()})  # GEO, GEO_S2_<station>, GEO_PROXY

QUANTIFIED = list(REL_SIGMA.keys())  # CLG, GAS, DSL, WOOD, GEO, GEO_S2_<station>, GEO_PROXY
print("REL_SIGMA (Approach 1 inputs, reused unchanged for Approach 2):")
for f, v in REL_SIGMA.items():
    print(f"  {f}: {v*100:.2f}%")

# Load data, pivot to wide contribution (co2_kg) and generation matrices
print("\nLoading hourly_fuel_mix_uncertainty.csv...")
df = pd.read_csv(HERE / "hourly_fuel_mix_uncertainty.csv")  # GEO split into GEO / GEO_PROXY
df["year"] = df["date"].str[:4].astype(int)
df["month"] = df["date"].str[5:7].astype(int)

idx_cols = ["island", "date", "hour", "year", "month"]
meta = df[idx_cols].drop_duplicates().sort_values(["island", "date", "hour"]).reset_index(drop=True)

contrib = df.pivot_table(index=["island", "date", "hour"], columns="fuel_std", values="co2_kg",
                          aggfunc="sum", fill_value=0.0)
gen = df.pivot_table(index=["island", "date", "hour"], columns="fuel_std", values="gen_mwh",
                      aggfunc="sum", fill_value=0.0)
contrib = contrib.reindex(meta.set_index(["island", "date", "hour"]).index).fillna(0.0)
gen = gen.reindex(contrib.index).fillna(0.0)
total_gen = gen.sum(axis=1).values
point_ef = contrib.sum(axis=1).values / np.where(total_gen > 0, total_gen, np.nan)

fuels_present = list(contrib.columns)
quant_cols = [f for f in QUANTIFIED if f in fuels_present]
det_cols = [f for f in fuels_present if f not in quant_cols]
print(f"\nQuantified (Monte Carlo) fuels: {quant_cols}")
print(f"Deterministic (point-value) fuels: {det_cols}")

Cq = contrib[quant_cols].values.astype(np.float64)          # (n_rows, k)
Cd_sum = contrib[det_cols].values.sum(axis=1).astype(np.float64)  # (n_rows,)
n_rows = Cq.shape[0]
k = len(quant_cols)

# Draw one multiplier per fuel per trial: lognormal, E[mult]=1, CV=rel_sigma
rng = np.random.default_rng(SEED)
sigma_ln = np.array([math.sqrt(math.log(1 + REL_SIGMA[f] ** 2)) for f in quant_cols])
mu_ln = -0.5 * sigma_ln ** 2
Z = rng.standard_normal((k, N_TRIALS))
mult = np.exp(mu_ln[:, None] + sigma_ln[:, None] * Z).astype(np.float64)  # (k, N_TRIALS), all > 0

print(f"\nRunning Monte Carlo: {n_rows:,} hourly rows x {N_TRIALS:,} trials, chunk={CHUNK}...")
p2_5 = np.empty(n_rows); p50 = np.empty(n_rows); p97_5 = np.empty(n_rows)
mc_mean = np.empty(n_rows); mc_std = np.empty(n_rows)

for start in range(0, n_rows, CHUNK):
    end = min(start + CHUNK, n_rows)
    chunk_draws = Cq[start:end] @ mult                      # (chunk, N_TRIALS)
    chunk_draws += Cd_sum[start:end, None]
    tg = total_gen[start:end, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        chunk_ef = np.where(tg > 0, chunk_draws / tg, np.nan)
    # one call for all three cuts: same values as three separate calls, one sort
    q = np.nanpercentile(chunk_ef, [2.5, 50, 97.5], axis=1)
    p2_5[start:end], p50[start:end], p97_5[start:end] = q[0], q[1], q[2]
    mc_mean[start:end] = np.nanmean(chunk_ef, axis=1)
    mc_std[start:end] = np.nanstd(chunk_ef, axis=1)
    if (start // CHUNK) % 40 == 0:
        print(f"  ...{end:,}/{n_rows:,} rows")

hourly_out = meta.copy()
hourly_out["total_gen_mwh"] = total_gen
hourly_out["point_ef_kg_per_mwh"] = point_ef
hourly_out["mc_mean_kg_per_mwh"] = mc_mean
hourly_out["mc_p2_5_kg_per_mwh"] = p2_5
hourly_out["mc_p50_kg_per_mwh"] = p50
hourly_out["mc_p97_5_kg_per_mwh"] = p97_5
hourly_out["mc_ci95_width_kg_per_mwh"] = p97_5 - p2_5
hourly_out["mc_ci95_pct_of_point"] = np.where(
    point_ef > 0, hourly_out["mc_ci95_width_kg_per_mwh"] / point_ef * 100.0, np.nan
)
hourly_out["mc_lower_bound_negative"] = p2_5 < 0
hourly_out.to_csv(HERE / "ipcc_uncertainty_by_island_hour_montecarlo.csv", index=False)
print(f"\nWrote ipcc_uncertainty_by_island_hour_montecarlo.csv ({len(hourly_out):,} rows)")

n_neg_mc = int(hourly_out["mc_lower_bound_negative"].sum())
print(f"Hours with a negative MC lower bound: {n_neg_mc} (by construction of the lognormal, should be 0)")

# Compare directly against Approach 1's full-coverage hourly result
a1_path = HERE / "ipcc_uncertainty_by_island_hour_full_coverage.csv"
if a1_path.exists():
    a1 = pd.read_csv(a1_path)
    a1["ci95_lower_kg_per_mwh"] = a1["point_ef_kg_per_mwh"] - 1.96 * a1["sigma_kg_per_mwh"]
    a1_neg = a1[a1["ci95_lower_kg_per_mwh"] < 0]
    merged = hourly_out.merge(
        a1[["island", "date", "hour", "point_ef_kg_per_mwh", "ci95_pct_of_point", "ci95_lower_kg_per_mwh"]],
        on=["island", "date", "hour"], suffixes=("", "_approach1"),
    )
    print(f"\n=== Approach 1 and Approach 2 (Monte Carlo), NI+SI hourly ===")
    a1_ni = a1[a1.island == "NI"]
    a1_ni_neg = a1_ni[a1_ni["ci95_lower_kg_per_mwh"] < 0]
    print(f"Approach 1, NI only: {len(a1_ni_neg):,} of {len(a1_ni):,} hours "
          f"({len(a1_ni_neg)/len(a1_ni)*100:.1f}%) have a negative lower bound")
    print(f"Approach 1, NI+SI combined denominator (for reference): {len(a1_neg):,} of {len(a1):,} "
          f"({len(a1_neg)/len(a1)*100:.1f}%); all {len(a1_neg):,} are NI hours, since geothermal is NI-only")
    print(f"Approach 2: {n_neg_mc} of {len(hourly_out):,} hours have a negative lower bound (fixed by construction)")
    ni = merged[merged.island == "NI"]
    print(f"\nNI mean CI width, Approach 1 (full coverage): {ni['ci95_pct_of_point'].mean():.2f}% of point")
    print(f"NI mean CI width, Approach 2 (Monte Carlo):    {ni['mc_ci95_pct_of_point'].mean():.2f}% of point")
    prev_bad = ni[ni["ci95_lower_kg_per_mwh"] < 0]
    if len(prev_bad):
        print(f"\nOf the {len(prev_bad):,} NI hours Approach 1 flagged as physically invalid:")
        print(f"  Approach 2 median CI width there: {prev_bad['mc_ci95_pct_of_point'].median():.1f}% of point")
        print(f"  Approach 2 lower bound is always >= 0 (guaranteed by the lognormal's support)")
    merged.to_csv(HERE / "ipcc_uncertainty_approach1_vs_approach2_hourly.csv", index=False)
    print("Wrote ipcc_uncertainty_approach1_vs_approach2_hourly.csv")
else:
    print(f"\n{a1_path.name} not found; skipping the Approach 1 and 2 comparison.")

# Monthly and annual roll-ups use the same trials (the correct treatment of a
# systematic, fixed-for-the-study parameter uncertainty; see module docstring).
def rollup(group_cols, label):
    g_contrib_q = pd.DataFrame(Cq, columns=quant_cols)
    g_contrib_q[group_cols] = meta[group_cols].values
    g_det = pd.DataFrame({"det": Cd_sum})
    g_det[group_cols] = meta[group_cols].values
    g_gen = pd.DataFrame({"gen": total_gen})
    g_gen[group_cols] = meta[group_cols].values

    aq = g_contrib_q.groupby(group_cols, sort=False)[quant_cols].sum()
    ad = g_det.groupby(group_cols, sort=False)["det"].sum()
    ag = g_gen.groupby(group_cols, sort=False)["gen"].sum()
    keys = aq.index
    Aq = aq.values
    Ad = ad.reindex(keys).values
    Ag = ag.reindex(keys).values

    draws = Aq @ mult + Ad[:, None]
    tg = Ag[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        ef_draws = np.where(tg > 0, draws / tg, np.nan)
    point = (Aq.sum(axis=1) + Ad) / np.where(Ag > 0, Ag, np.nan)

    out = keys.to_frame(index=False)
    out["total_gen_mwh"] = Ag
    out["point_ef_kg_per_mwh"] = point
    out["mc_mean_kg_per_mwh"] = np.nanmean(ef_draws, axis=1)
    out["mc_p2_5_kg_per_mwh"] = np.nanpercentile(ef_draws, 2.5, axis=1)
    out["mc_p50_kg_per_mwh"] = np.nanpercentile(ef_draws, 50, axis=1)
    out["mc_p97_5_kg_per_mwh"] = np.nanpercentile(ef_draws, 97.5, axis=1)
    out["mc_ci95_width_kg_per_mwh"] = out["mc_p97_5_kg_per_mwh"] - out["mc_p2_5_kg_per_mwh"]
    out["mc_ci95_pct_of_point"] = np.where(
        out["point_ef_kg_per_mwh"] > 0, out["mc_ci95_width_kg_per_mwh"] / out["point_ef_kg_per_mwh"] * 100.0, np.nan
    )
    out.to_csv(HERE / f"ipcc_uncertainty_by_island_{label}_montecarlo.csv", index=False)
    print(f"\nWrote ipcc_uncertainty_by_island_{label}_montecarlo.csv ({len(out)} rows)")
    ni_out = out[out.island == "NI"]
    print(f"NI {label} CI% (Monte Carlo): min={ni_out['mc_ci95_pct_of_point'].min():.2f}% "
          f"max={ni_out['mc_ci95_pct_of_point'].max():.2f}% mean={ni_out['mc_ci95_pct_of_point'].mean():.2f}%")
    return out

print("\n=== Monthly roll-up ===")
rollup(["island", "year", "month"], "month")
print("\n=== Annual roll-up ===")
rollup(["island", "year"], "year")

print("\nDone.")
