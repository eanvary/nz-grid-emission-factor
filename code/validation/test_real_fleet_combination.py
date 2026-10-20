"""
Rather than assuming plants combine as an unweighted population spread
(build_fleet_uncertainty.py's cross-sectional proxy) or an IPCC-default range, this
script measures how the gas fleet's plants combine and how much the blended EF moves
because of it.

Two quantities, both computed from data:

1. Per-POC generation share within the gas fleet, 2015-2025. This shows whether a few
   plants dominate (concentration) or generation spreads evenly across all 11.
2. The observed month-to-month and hour-to-hour blended gas EF. This is not a model: it
   is the generation-weighted average of whichever plants ran, as build_ef_timeseries*.py
   computes it, with the pipeline's shared generation reader and attribution
   (generation_pipeline/fuel_attribution.py: flagged fills included, generator- and
   unit-level factors, and the gas portion of Huntly 1-4 counted as gas). Its empirical
   standard deviation measures how much the combination has varied historically.

Conceptual distinction (read before reusing #2 as an "uncertainty"): the point EF for
any historical period is not itself uncertain. It is a deterministic function of which
plants ran (known) and their registered EF (taken as ground truth). The empirical std of
the series in #2 therefore measures dispatch volatility. That is a different quantity
from "how wrong might the register's EF values be", the epistemic quantity that IPCC
Table 2.2's default range and build_fleet_uncertainty.py's cross-sectional spread both
approximate. The two are reported side by side below.
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import FuelAttribution, poc_island_map  # noqa: E402

OUT = HERE / "gas_real_plant_shares.csv"

fa = FuelAttribution()
print("Loading Generation_MD files and flagged fills (via fuel_attribution), keeping attributed GAS rows...")
gen = fa.generation(level="month", include_fills=True)
gen["island"] = gen["poc"].map(poc_island_map())
gen = gen[gen["island"].isin(["NI", "SI"])]
gen = gen.groupby(["poc", "gen_code", "fuel_std", "year", "month"], as_index=False)["gen_mwh"].sum()
monthly = fa.attribute(gen)
monthly = monthly[monthly["fuel_std"] == "GAS"]
monthly = monthly.rename(columns={"poc": "POC_Code", "ef_kg_per_mwh": "ef"})

# 1. Generation share per POC, whole period (concentration check)
share = monthly.groupby("POC_Code")["gen_mwh"].sum().sort_values(ascending=False)
share_pct = (share / share.sum() * 100).round(2)
print("\n=== Generation share by gas POC, 2015-2025 (concentration) ===")
print(share_pct.to_string())
top2_share = share_pct.iloc[:2].sum()
print(f"\nTop 2 plants' combined share: {top2_share:.1f}% of all gas generation")
share_pct.to_csv(OUT, header=["share_pct"])

# 2. Blended monthly EF, generation-weighted. It should reproduce the GAS row of
#    monthly_fuel_mix_NI_SI.csv, as a cross-check against the published table.
monthly_blend = monthly.groupby(["year", "month"]).apply(
    lambda g: (g["gen_mwh"] * g["ef"]).sum() / g["gen_mwh"].sum(), include_groups=False
)
print(f"\n=== Blended monthly GAS EF (recomputed here, independent of monthly_fuel_mix_NI_SI.csv) ===")
print(f"n={len(monthly_blend)}, mean={monthly_blend.mean():.2f}, std={monthly_blend.std():.2f}, "
      f"rel_std={monthly_blend.std()/monthly_blend.mean()*100:.2f}%")

mm_released = pd.read_csv(ROOT / "output" / "monthly_fuel_mix_NI_SI.csv")
released_gas = mm_released[(mm_released.island == "NI") & (mm_released.fuel_code == "GAS")]["weighted_ef_kg_per_MWh"].dropna()
print(f"Released monthly_fuel_mix_NI_SI.csv GAS row: mean={released_gas.mean():.2f}, "
      f"std={released_gas.std():.2f}, rel_std={released_gas.std()/released_gas.mean()*100:.2f}% "
      f"(cross-check: should closely match the line above)")
