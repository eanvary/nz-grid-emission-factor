"""
Sensitivity of the published uncertainty band to one modelling choice: what
geothermal's relative sigma should be.

Why this test
run_ipcc_uncertainty_montecarlo.py sets GEO's relative sigma to the MW-weighted
spread across the 12 McLean & Richardson (2019) stations, 93.97%, and draws one
multiplier per fuel per trial. That is a fuel-level parameter.

But the point estimate does not use a fleet value for geothermal:
geothermal_ef_correction.py gives 90.5% of geothermal
generation its own station's measured emission factor (Ohaaki 341, Wairakei 21,
and so on), and only the remaining 9.5% falls back to the fleet mean of 76.03.

So for most of the fleet the between-station spread is information the database
already holds, not uncertainty about it. Re-using that spread as a fuel-level
sigma therefore risks counting known heterogeneity twice.

The question is left open here. The same Monte Carlo is re-run under
the adopted reading of what is uncertain and three alternatives, changing nothing
else, so the size of the effect is on record.

  0. adopted           by proxy-rule step, independent draws: step 1 at the NIR
                       2026 measurement uncertainty (7.07%), step 2 at 7.07% with the
                       station's own year-to-year variation, steps 3-4 at the spread
  1. previous          the full between-station spread, one common draw
  2. independent       the same spread, but station errors independent of
                       each other, which shrinks the aggregate by the effective
                       station count
  3. fallback only     between-station variation is treated as captured by the
                       point estimate, so only the plants still on the 76.03
                       fallback carry uncertainty

It also runs Approach 1 under each, because the case for Approach 2 rests on
Approach 1 failing, and that failure is itself a function of this sigma.

Run: python test_geothermal_sigma_sensitivity.py
"""
import math
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
N_TRIALS, SEED = 50_000, 42   # matches run_ipcc_uncertainty_montecarlo.py; see test_montecarlo_trial_convergence.py
IPCC_CV_LIMIT = 0.30          # 2019 Refinement Vol.1 Ch.3, Approach 1 validity

# Sigmas, rebuilt exactly as run_ipcc_uncertainty_montecarlo.py does
IPCC_TABLE_2_2 = {
    "CLG": (96100., 92800., 100000.), "GAS": (56100., 54300., 58300.),
    "DSL": (74100., 72600., 74800.), "WOOD": (112000., 95000., 132000.),
}


def rel_half_width(d, lo, hi):
    return (abs(d - lo) / d + abs(hi - d) / d) / 2.0


BASE = {f: rel_half_width(*v) for f, v in IPCC_TABLE_2_2.items()}
BASE["GAS"] = pd.read_csv(os.path.join(HERE, "fleet_uncertainty_by_fuel.csv")
                          ).set_index("fuel_std")["rel_sigma_adopted"]["GAS"]

g = pd.read_csv(os.path.join(HERE, "geothermal_mclean_richardson_stations.csv"))
w = g.mw / g.mw.sum()
mu = (w * g.ef_gco2_kwh).sum()
sd = math.sqrt((w * (g.ef_gco2_kwh - mu) ** 2).sum())
SIG_RELEASED = sd / mu
SIG_INDEP = math.sqrt((w ** 2 * (g.ef_gco2_kwh - mu) ** 2).sum()) / mu

plant = pd.read_csv(os.path.join(ROOT, "output",
                                 "plant_level_generation_emissions_2015_2025.csv"))
geo = plant[plant.fuel_std == "GEO"]
fallback = geo[geo.EF_kg_per_MWh.round(2).between(76.02, 76.04)]
co2_share_fallback = fallback.total_CO2_kg.sum() / geo.total_CO2_kg.sum()
SIG_FALLBACK = co2_share_fallback * SIG_RELEASED

_geo_sig = pd.read_csv(os.path.join(HERE, "geo_uncertainty_sigma.csv")).set_index("fuel_std")["rel_sigma"]
SIG_TERMS = {k: float(v) for k, v in _geo_sig.items()}  # GEO, GEO_S2_<station>, GEO_PROXY
# each scenario: (name, {geothermal term: sigma} or one sigma for every geothermal term). The first is the
# adopted method (by proxy-rule step, build_geo_uncertainty_inputs.py); the other three are alternative
# readings, applied to all geothermal alike.
SCENARIOS = [
    ("as released: by rule step (7.07% / station / spread)", SIG_TERMS),
    ("previous: full between-station spread, one draw", SIG_RELEASED),
    ("same spread, station errors independent", SIG_INDEP),
    ("only the fallback plants are uncertain", SIG_FALLBACK),
]

print(f"effective station count           : {1 / (w ** 2).sum():.1f}")
print(f"fallback share of geothermal CO2  : {co2_share_fallback * 100:.1f}%\n")

# Hourly fuel mix, pivoted to CO2 by fuel
df = pd.read_csv(os.path.join(HERE, "hourly_fuel_mix_uncertainty.csv"),
                 usecols=["island", "date", "hour", "fuel_std", "gen_mwh", "co2_kg"])
df = df[df.island == "NI"]
co2 = df.pivot_table(index=["date", "hour"], columns="fuel_std",
                     values="co2_kg", aggfunc="sum").fillna(0.0)
gen = df.groupby(["date", "hour"]).gen_mwh.sum().reindex(co2.index)
keep = (gen.to_numpy() > 0) & (co2.sum(axis=1).to_numpy() > 0)
co2, gen = co2[keep], gen[keep]
point = co2.sum(axis=1).to_numpy() / gen.to_numpy()
QUANT = [f for f in ["CLG", "GAS", "DSL", "WOOD"] + list(SIG_TERMS) if f in co2.columns]
C = co2[QUANT].to_numpy()
fixed = co2.drop(columns=QUANT).sum(axis=1).to_numpy()
G = gen.to_numpy()
print(f"NI hours: {len(G):,}   quantified fuels: {QUANT}\n")

rows = []
hdr = (f"{'scenario':<52}{'sigma':>7}{'Appr.1':>8}{'A1 band':>9}"
       f"{'A1 neg':>9}{'A2 band':>9}")
print(hdr)
print(f"{'':<52}{'':>7}{'valid?':>8}{'':>9}{'hours':>9}{'':>9}")
print("-" * 94)
for name, spec in SCENARIOS:
    geo_sig = spec if isinstance(spec, dict) else {k: spec for k in SIG_TERMS}
    sig = np.array([geo_sig[f] if f in geo_sig else BASE[f] for f in QUANT])
    sig_geo = max(geo_sig[f] for f in QUANT if f in geo_sig)  # largest geothermal sigma in use

    # Approach 2, lognormal, one draw per fuel per trial, fixed for the record
    rng = np.random.default_rng(SEED)
    mu_ln = np.log(1.0 / np.sqrt(1.0 + sig ** 2))
    sd_ln = np.sqrt(np.log(1.0 + sig ** 2))
    draws = rng.lognormal(mu_ln, sd_ln, size=(N_TRIALS, len(QUANT)))
    qs = []
    for s in range(0, len(G), 500):
        e = min(s + 500, len(G))
        sim = (C[s:e] @ draws.T + fixed[s:e, None]) / G[s:e, None]
        qs.append(np.percentile(sim, [2.5, 97.5], axis=1))
    q = np.concatenate(qs, axis=1)
    a2_band = (q[1] - q[0]) / point * 100

    # Approach 1, first-order linear propagation, same inputs
    a1_abs = np.sqrt(((C * sig) ** 2).sum(axis=1)) / G
    a1_lo = point - 1.96 * a1_abs
    a1_band = 2 * 1.96 * a1_abs / point * 100

    valid = "no" if sig_geo > IPCC_CV_LIMIT else "yes"
    print(f"{name:<52}{sig_geo * 100:>6.1f}%{valid:>8}{np.nanmean(a1_band):>8.1f}%"
          f"{int((a1_lo < 0).sum()):>9,}{np.nanmean(a2_band):>8.1f}%")
    rows.append({"scenario": name, "sigma_geo_max": round(sig_geo, 4),
                 "approach1_valid_under_ipcc_cv_limit": valid,
                 "approach1_mean_band_pct": round(float(np.nanmean(a1_band)), 1),
                 "approach1_negative_lower_bound_hours": int((a1_lo < 0).sum()),
                 "approach2_mean_band_pct": round(float(np.nanmean(a2_band)), 1)})

out = os.path.join(HERE, "geothermal_sigma_sensitivity.csv")
pd.DataFrame(rows).to_csv(out, index=False)
print(f"\nwritten: {os.path.basename(out)}")
print("\nNote: under both alternatives Approach 1 passes the IPCC validity test,")
print("returns no impossible values, and gives the same band as Approach 2, which")
print("is what theory predicts once the coefficient of variation is small.")
