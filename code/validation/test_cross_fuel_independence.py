"""
Tests the assumption that fuel-to-fuel EF errors are independent against the monthly
per-fuel EF series in monthly_fuel_mix_NI_SI.csv.

What "cross-fuel independence" means in the propagation formula (run_ipcc_uncertainty_
quantification.py): Var(EF) = sum_i (w_i * sigma_i)^2 requires each fuel's own EF-value
error to be uncorrelated with every other fuel's. This can only be tested on the variation
each fuel's registered EF shows over the 132-month study period. The first check is
therefore whether each fuel varies at all.
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "cross_fuel_correlation.csv"

mm = pd.read_csv(ROOT / "output" / "monthly_fuel_mix_NI_SI.csv")
ni = mm[mm.island == "NI"].copy()
ni["period"] = pd.to_datetime(dict(year=ni.year, month=ni.month, day=1))

FUELS = ["CLG", "GAS", "DSL", "WOOD"]
series = {}
for fuel in FUELS:
    s = ni[ni.fuel_code == fuel].set_index("period")["weighted_ef_kg_per_MWh"]
    series[fuel] = pd.to_numeric(s, errors="coerce")

panel = pd.DataFrame(series).sort_index()

print("=== Step 1: does each fuel's registered EF vary at all? (measured) ===")
summary_rows = []
for fuel in FUELS:
    s = panel[fuel].dropna()
    std = s.std()
    n_distinct = s.round(6).nunique()
    varies = std is not None and std > 1e-6
    summary_rows.append({"fuel": fuel, "n_months": len(s), "mean": s.mean(), "std": std,
                          "n_distinct_values": n_distinct, "varies": varies})
    tag = "VARIES -- real signal" if varies else "CONSTANT -- no variation to correlate"
    print(f"  {fuel}: n={len(s)}, mean={s.mean():.2f}, std={std:.6f}, "
          f"{n_distinct} distinct value(s) -> {tag}")

summary = pd.DataFrame(summary_rows)
summary.to_csv(OUT.with_name("cross_fuel_variation_summary.csv"), index=False)

varying_fuels = summary[summary.varies]["fuel"].tolist()
print(f"\nFuels with any variation to test for cross-correlation: {varying_fuels}")

print("\n=== Step 2: pairwise correlation ===")
corr_raw = panel.corr()
print("Raw pandas .corr() output (includes an artefact, explained below):")
print(corr_raw.round(4).to_string())

# CLG and DSL are not bit-identical constants: their std is about 5e-14 and 7e-14
# (float rounding noise from repeating the same HeatRate*EmissionsFactor/1e6
# division every month), not variation. Pearson correlation divides by std,
# so these near-zero but nonzero denominators turn floating-point noise into
# plausible-looking coefficients (-0.07, 0.02 above) that mean nothing. Any
# pair involving a fuel that the first check flagged CONSTANT is set to NaN
# here rather than reported at face value.
corr = corr_raw.copy()
for fuel in FUELS:
    if fuel not in varying_fuels:
        corr.loc[fuel, :] = np.nan
        corr.loc[:, fuel] = np.nan
        corr.loc[fuel, fuel] = np.nan  # self-correlation of a constant is undefined too
print("\nCorrected (constant-fuel pairs set to NaN to remove floating-point noise):")
print(corr.round(4).to_string())
corr.to_csv(OUT)

print("\n=== Verdict ===")
if len(varying_fuels) <= 1:
    print(f"Only {len(varying_fuels)} of 4 combustion fuels ({varying_fuels}) show any "
          f"month-to-month variation in this project's data (the others carry one constant "
          f"factor). Cross-fuel independence cannot be violated when only one variable "
          f"varies: there is nothing for it to correlate with.")
else:
    print(f"More than one fuel varies ({varying_fuels}); the correlation values above are the "
          f"test result.")

print("\n=== Side finding, checked for WOOD: ===")
wood_co2 = ni[ni.fuel_code == "WOOD"]["co2_kg"]
wood_gen = ni[ni.fuel_code == "WOOD"]["gen_mwh"]
wood_ef = ni[ni.fuel_code == "WOOD"]["weighted_ef_kg_per_MWh"]
# Kinleith wood carries CH4 and N2O only (biogenic CO2 excluded): 1.52 kg/GJ x
# MBIE's wood heat rate for the year (override KINLEITH_WOOD, generation_pipeline/
# fuel_attribution_overrides.csv), so its factor is non-zero and changes year to year.
print(f"WOOD generation: {wood_gen.mean():,.0f} MWh/month on average "
      f"({wood_gen.min():,.0f}-{wood_gen.max():,.0f} MWh); CO2e = {wood_co2.sum() / 1e6:,.1f} kt in total; "
      f"EF {wood_ef.min():.2f}-{wood_ef.max():.2f} kg/MWh (CH4 and N2O only, KINLEITH_WOOD). "
      f"The WOOD rel_sigma therefore contributes to the propagated CI (sigma_i = ef_i x rel_sigma), "
      f"a small term given wood's share of generation.")
