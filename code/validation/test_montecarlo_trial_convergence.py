"""
How many Monte Carlo trials does the reported uncertainty band actually need?

WHY THIS EXISTS (2026-09-23)
run_ipcc_uncertainty_montecarlo.py originally set N_TRIALS to 10,000. Nothing in the
script said why. 10,000 is the common round default, so the number was a convention
rather than a measured choice, and a reported band of 73.2% implies a precision that
had never been checked.

Two features of this design make a modest trial count less safe than it looks.

  1. One multiplier per fuel is drawn per trial and held across the whole record. Every
     hour therefore shares the same N draws, so the sampling error in the percentiles is
     common to all hours. Averaging over 96,421 hours cancels none of it. This is the
     usual reason a modest N is safe, and here it does not apply.

  2. Geothermal on proxy-rule steps 3-4 carries a 93.97% sigma (since 2026-09-29 step 1
     carries 7.07%, NIR 2026, and step 2 7.07% plus the station's own variation), which
     gives the lognormal a heavy right tail
     exactly where the 2.5 and 97.5 cuts sit. Extreme percentiles of a heavy tail are the
     slowest quantities to settle.

The test runs the same Monte Carlo at a range of trial counts, three seeds each, and
reports how far the mean 95% band width moves with the seed alone. Seed spread is the
quantity of interest: a fixed SEED makes a run reproducible, which is not the same as
converged.

A 3,000-hour random sample stands in for the full record. That is sound here precisely
because of point 1: the error is common across hours, so sampling hours does not bias
the measurement of it.

Run: python test_montecarlo_trial_convergence.py
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
N_HOURS = 3_000          # sample of NI hours, see docstring
HOUR_SEED = 0
TRIAL_SEEDS = (1, 2, 3)
TRIAL_COUNTS = (500, 1_000, 2_000, 5_000, 10_000, 50_000, 200_000)

# Sigmas, rebuilt exactly as run_ipcc_uncertainty_montecarlo.py does
IPCC_TABLE_2_2 = {
    "CLG": (96100., 92800., 100000.), "GAS": (56100., 54300., 58300.),
    "DSL": (74100., 72600., 74800.), "WOOD": (112000., 95000., 132000.),
}


def rel_half_width(d, lo, hi):
    return (abs(d - lo) / d + abs(hi - d) / d) / 2.0


REL_SIGMA = {f: rel_half_width(*v) for f, v in IPCC_TABLE_2_2.items()}
REL_SIGMA["GAS"] = pd.read_csv(os.path.join(HERE, "fleet_uncertainty_by_fuel.csv")
                               ).set_index("fuel_std")["rel_sigma_adopted"]["GAS"]

g = pd.read_csv(os.path.join(HERE, "geothermal_mclean_richardson_stations.csv"))
w = g.mw / g.mw.sum()
mu = (w * g.ef_gco2_kwh).sum()
_geo_sig = pd.read_csv(os.path.join(HERE, "geo_uncertainty_sigma.csv")).set_index("fuel_std")["rel_sigma"]
REL_SIGMA.update({k: float(v) for k, v in _geo_sig.items()})  # geothermal by proxy-rule step (build_geo_uncertainty_inputs.py)

# Hourly fuel mix, pivoted to CO2 by fuel
df = pd.read_csv(os.path.join(HERE, "hourly_fuel_mix_uncertainty.csv"),
                 usecols=["island", "date", "hour", "fuel_std", "gen_mwh", "co2_kg"])
df = df[df.island == "NI"]
co2 = df.pivot_table(index=["date", "hour"], columns="fuel_std",
                     values="co2_kg", aggfunc="sum").fillna(0.0)
gen = df.groupby(["date", "hour"]).gen_mwh.sum().reindex(co2.index)
keep = (gen.to_numpy() > 0) & (co2.sum(axis=1).to_numpy() > 0)
co2, gen = co2[keep], gen[keep]

QUANT = [f for f in REL_SIGMA if f in co2.columns]
idx = np.random.default_rng(HOUR_SEED).choice(len(gen), N_HOURS, replace=False)
C = co2[QUANT].to_numpy()[idx]
fixed = co2.drop(columns=QUANT).sum(axis=1).to_numpy()[idx]
G = gen.to_numpy()[idx]
point = (C.sum(axis=1) + fixed) / G

sig = np.array([REL_SIGMA[f] for f in QUANT])
sd_ln = np.sqrt(np.log(1.0 + sig ** 2))
mu_ln = -0.5 * sd_ln ** 2

print(f"NI hours sampled: {N_HOURS:,} of {len(gen):,}   quantified fuels: {QUANT}")
print(f"geothermal sigma: step 1 {REL_SIGMA['GEO'] * 100:.2f}%, step 2 by station, steps 3-4 {REL_SIGMA['GEO_PROXY'] * 100:.2f}%\n")
print("mean 95% band width, as a percentage of the point estimate")
head = f"{'trials':>9}" + "".join(f"{'seed ' + str(s):>10}" for s in TRIAL_SEEDS)
print(head + f"{'spread':>10}")
print("-" * len(head + f"{'spread':>10}"))

rows = []
for n in TRIAL_COUNTS:
    vals = []
    for seed in TRIAL_SEEDS:
        d = np.random.default_rng(seed).lognormal(mu_ln, sd_ln, size=(n, len(QUANT)))
        bands = []
        for s in range(0, len(G), 500):                  # chunk over hours, memory
            e = min(s + 500, len(G))
            sim = (C[s:e] @ d.T + fixed[s:e, None]) / G[s:e, None]
            q = np.percentile(sim, [2.5, 97.5], axis=1)
            bands.append((q[1] - q[0]) / point[s:e] * 100)
        vals.append(float(np.mean(np.concatenate(bands))))
    spread = max(vals) - min(vals)
    print(f"{n:>9,}" + "".join(f"{v:>9.2f}%" for v in vals) + f"{spread:>9.2f}pp")
    rows.append({"n_trials": n,
                 **{f"band_pct_seed_{s}": round(v, 2)
                    for s, v in zip(TRIAL_SEEDS, vals)},
                 "seed_spread_pp": round(spread, 2)})

out = os.path.join(HERE, "montecarlo_trial_convergence.csv")
pd.DataFrame(rows).to_csv(out, index=False)
print(f"\nwritten: {os.path.basename(out)}")
print("\nReading it: 'spread' is how far the reported band moves when only the random")
print("seed changes. It is the precision of the reported number. A run is converged")
print("when that spread is small next to the precision the band is quoted at.")
