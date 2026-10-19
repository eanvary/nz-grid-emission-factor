"""
Replaces IPCC's borrowed Tier-1 default uncertainty range with a measured, NZ-fleet-
specific one wherever the data actually supports it, per IPCC's own guidance (2006 GL
Vol 2 Ch 2, Section 2.3.2.2): "it is expected that the uncertainty range associated with
a country-specific value will be smaller than the uncertainty range of the default
emission factor."

The plant register (EA data/Dispatched generation
plant.csv, as corrected and loaded by generation_pipeline/fuel_attribution.py: MfE 2025
combustion factors, heat-rate and decommissioning fixes) gives this project's own EF per
(POC, fuel). The census printed below counts, per fuel, the distinct POCs and distinct
register EF values. With the raw register EFs the census gives:
  - Coal (CLG): 1 distinct POC (Huntly Rankine) -- a single value, zero spread.
  - Diesel (DSL): 1 distinct POC -- likewise zero spread.
  - Gas (GAS): 13 distinct POCs, 8 distinct EF values, 385-560 kg/MWh -- a real fleet.
  - Wood (WOOD): not in the thermal SCD2 register at all.
So only GAS gets a fleet-specific replacement here. Forcing a "fleet spread" for a
single-plant fuel would produce a false zero-uncertainty band, not a tighter one
(worse than IPCC's default, not better), so CLG/DSL/WOOD keep the IPCC Table 2.2
range used by the other propagation scripts.

Method: generation-weighted mean and standard deviation of each thermal fuel's per-plant
per-month EF, as the pipeline assigns it (fuel_attribution.FuelAttribution.attribute:
generator- and unit-level factors, Huntly 1-4 coal/gas split with the gas portion counted
under GAS, flagged fills included), weighted by each (POC, generator, year, month) cell's
own generation -- so a large, heavily-used plant counts more than a rarely-dispatched
peaker, and a degenerate/undersampled result would show up as a small n or a
suspiciously tight range, not be hidden. Cells with a zero factor (e.g. Glenbrook, zero
by the pipeline's own rule) carry no register EF and are left out.

Adopted gas sigma: per-unit factor uncertainty, not fleet dispersion. Since the
pipeline gives each unit its own factor, the spread between units is known heterogeneity, not
uncertainty in any unit's factor; using it as the gas sigma double-counts. The adopted value is
  rel_sigma_adopted(GAS) = sqrt(carbon^2 + heatrate^2)
  carbon   = IPCC (2006) Vol 2 Ch 2 Table 2.2 natural gas, default 56,100 kg/TJ (54,300-58,300),
             as the relative half-width used by the existing propagation scripts (0.0357)
  heatrate = RMS of the D3 gas-fuel annual residuals, 2015-2025 (pipeline-implied gas PJ vs MBIE
             gas data tables, output/D3_fuel_level_validation.csv, check GAS-PJ)
Cross-check, printed: register vs MBIE generation stack heat rates for gas plants of the same
type after the HEATRATE_* corrections (MBIE 2011 Table 3-1; MBIE 2020 Tables 3-3 and 3-13).
rel_sigma_fleet (the dispersion) is kept in the output as a diagnostic; consumers read
rel_sigma_adopted.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import FuelAttribution, poc_island_map  # noqa: E402

OUT = HERE / "fleet_uncertainty_by_fuel.csv"

THERMAL_FUELS = {"CLG", "GAS", "DSL"}

fa = FuelAttribution()
thermal = fa.reg[fa.reg["EF_kg_per_MWh"].notna()]

print("Census (confirms the doc-string claim, not assumed):")
for fuel in ["CLG", "GAS", "DSL"]:
    t = thermal[thermal["FuelCode"] == fuel]
    vals = sorted(t["EF_kg_per_MWh"].unique())
    print(f"  {fuel}: {t['PointOfConnectionCode'].nunique()} distinct POC(s), {len(vals)} distinct EF value(s): {vals}")

print("\nLoading Generation_MD files and flagged fills (monthly per-generator totals, via fuel_attribution)...")
poc_island = poc_island_map()
gen = fa.generation(level="month", include_fills=True)
gen["island"] = gen["poc"].map(poc_island)
gen = gen[gen["island"].isin(["NI", "SI"])]
gen = gen.groupby(["poc", "gen_code", "fuel_std", "year", "month"], as_index=False)["gen_mwh"].sum()
monthly = fa.attribute(gen)
monthly = monthly[monthly["fuel_std"].isin(THERMAL_FUELS)]
monthly = monthly.rename(columns={"poc": "POC_Code", "ef_kg_per_mwh": "ef"})
monthly = monthly[monthly["ef"] > 0]  # drop cells with no register factor
print(f"  {len(monthly):,} (POC, generator, fuel, year, month) cells with an active thermal EF")

rows = []
for fuel, g in monthly.groupby("fuel_std"):
    total_gen = g["gen_mwh"].sum()
    w_mean = (g["gen_mwh"] * g["ef"]).sum() / total_gen
    w_var = (g["gen_mwh"] * (g["ef"] - w_mean) ** 2).sum() / total_gen
    w_std = np.sqrt(w_var)
    n_poc = g["POC_Code"].nunique()
    n_cells = len(g)
    rel_sigma = w_std / w_mean if w_mean > 0 else np.nan
    rows.append({
        "fuel_std": fuel, "n_distinct_poc": n_poc, "n_poc_month_cells": n_cells,
        "gen_weighted_mean_ef": w_mean, "gen_weighted_std_ef": w_std,
        "rel_sigma_fleet": rel_sigma, "total_gen_mwh": total_gen,
    })
result = pd.DataFrame(rows)

# Adopted gas sigma: per-unit factor uncertainty (carbon content + heat rate)
IPCC_GAS = (56100.0, 54300.0, 58300.0)  # IPCC 2006 Vol 2 Ch 2 Table 2.2, natural gas, kg CO2/TJ
carbon = (abs(IPCC_GAS[0] - IPCC_GAS[1]) + abs(IPCC_GAS[2] - IPCC_GAS[0])) / IPCC_GAS[0] / 2.0
d3 = pd.read_csv(ROOT / "output" / "D3_fuel_level_validation.csv")
d3 = d3[(d3["check"] == "GAS-PJ") & (d3["resolution"] == "annual")].copy()
d3["period"] = d3["period"].astype(int)
d3 = d3[d3["period"].between(2015, 2025)]
heatrate = float(np.sqrt((d3["gap_pct"] ** 2).mean()) / 100.0)
adopted = float(np.sqrt(carbon ** 2 + heatrate ** 2))
result["rel_sigma_carbon"] = np.where(result["fuel_std"] == "GAS", carbon, np.nan)
result["rel_sigma_heatrate"] = np.where(result["fuel_std"] == "GAS", heatrate, np.nan)
result["rel_sigma_adopted"] = np.where(result["fuel_std"] == "GAS", adopted, np.nan)
print(f"\nAdopted GAS rel_sigma = sqrt({carbon:.4f}^2 + {heatrate:.4f}^2) = {adopted:.4f} "
      f"(carbon: IPCC Table 2.2; heat rate: RMS of {len(d3)} D3 gas-fuel annual residuals, "
      f"{d3['period'].min()}-{d3['period'].max()}); fleet dispersion (diagnostic) = "
      f"{result.set_index('fuel_std')['rel_sigma_fleet'].get('GAS', np.nan):.4f}")

# cross-check: register vs MBIE heat rates, gas plants of the same type, after corrections
MBIE_HR = {  # unit(s): (MBIE heat rate GJ/GWh, source)
    "Huntly Rankine (gas)": (["HLY1"], 10900, "MBIE 2020 Table 3-3, Huntly gas units 1, 2 & 4, ST"),
    "Huntly 5 (e3p)": (["HLY5"], 7400, "MBIE 2020 Table 3-3, CCGT"),
    "Huntly 6 (P40)": (["HLY6"], 10525, "MBIE 2020 Table 3-3, OCGT"),
    "Taranaki CC": (["SPL0"], 7400, "MBIE 2020 Table 3-3, CCGT"),
    "Stratford peakers": (["SFD21", "SFD22"], 8907, "MBIE 2020 Table 3-3, OCGT (register corrected)"),
    "Te Rapa": (["TRC1"], 11700, "MBIE 2020 Table 3-13, cogenerator (register corrected)"),
    "Otahuhu B": (["OTC0"], 7400, "MBIE 2011 Table 3-1, CCGT (register corrected)"),
    "Southdown": (["SWN0"], 7400, "MBIE 2011 Table 3-1, CCGT (register corrected)"),
    "Southdown E105": (["SWN5"], 10600, "MBIE 2011 Table 3-1, OCGT (register corrected)"),
}
audit = []
for plant, (units, mbie, src) in MBIE_HR.items():
    reg_hr = float(fa.reg.loc[fa.reg["UnitCode"].isin(units), "HeatRate"].mean())
    audit.append({"plant": plant, "register_hr": reg_hr, "mbie_hr": mbie, "gap_pct": (reg_hr / mbie - 1) * 100, "source": src})
audit = pd.DataFrame(audit)
rms_all = float(np.sqrt((audit["gap_pct"] ** 2).mean()))
unc = audit[~audit["source"].str.contains("corrected")]
rms_unc = float(np.sqrt((unc["gap_pct"] ** 2).mean()))
print("\nCross-check, register vs MBIE heat rate after corrections (gas, same type):")
print(audit.round(2).to_string(index=False))
print(f"  RMS gap: {rms_all:.2f}% over {len(audit)} plants; {rms_unc:.2f}% over the {len(unc)} uncorrected plants "
      f"(D3 heat-rate term: {heatrate * 100:.2f}%)")
audit.to_csv(HERE / "gas_heat_rate_audit.csv", index=False, float_format="%.3f")

result.to_csv(OUT, index=False)
print(f"\nWrote fleet uncertainty by fuel -> {OUT}")
print(result.to_string(index=False))

print("\n=== Comparison: fleet-specific relative sigma vs. IPCC Table 2.2 default ===")
IPCC_REL_SIGMA = {"CLG": 0.0371, "GAS": 0.0356, "DSL": 0.0148}  # from run_ipcc_uncertainty_quantification.py
for _, row in result.iterrows():
    fuel = row["fuel_std"]
    ipcc = IPCC_REL_SIGMA.get(fuel)
    fleet = row["rel_sigma_fleet"]
    if fuel in ("CLG", "DSL") and row["n_distinct_poc"] <= 1:
        print(f"  {fuel}: single-plant fleet (n_poc={row['n_distinct_poc']}) -> fleet estimate is "
              f"DEGENERATE (rel_sigma={fleet:.4f}), NOT adopted; IPCC default ({ipcc:.4f}) retained.")
    else:
        verdict = "TIGHTER (adopt)" if fleet < ipcc else "WIDER than IPCC default (adopt anyway -- it's the real measured value)"
        print(f"  {fuel}: n_poc={row['n_distinct_poc']}, fleet rel_sigma={fleet:.4f} vs "
              f"IPCC default {ipcc:.4f} -> {verdict}")
