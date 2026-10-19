"""
Thermal plant efficiency improvement, as a standalone sensitivity test, not a pipeline
change. This script does not modify build_edgs_dispatch.py, edgs_common.py,
build_edgs_plant_register.py, or any pipeline output parquet. It reads only the pipeline's
saved intermediates and recomputes combustion CO2 in parallel under a counterfactual
efficiency-improvement assumption, for comparison against the baseline.

Background: does the pipeline account for thermal plants getting more efficient over
2024-2050? Both MBIE source workbooks say no, and not because the pipeline dropped it: MBIE's
Generation Stack `Heat Rate (GJ/GWh)` field is a single static value per plant, identical
across all 5 scenarios, with no year dimension (e.g. Huntly Rankine coal = 10900 GJ/GWh in
every scenario/row; Huntly U5 CCGT = 7400 in every scenario/row). The only new thermal builds
in the whole stack are 8 generic OCGT peakers, all fixed at 11750 GJ/GWh, worse than most
existing plants. MBIE's published `Emission factors` sheet trend to 2050 is explained by the
shift in fleet mix (more renewables, thermal retirements), not by any per-plant efficiency
assumption. So there is no MBIE efficiency trend to extract; modelling one needs an external,
cited assumption, like the geothermal/wood/battery external constants in edgs_common.py. This
script builds and tests one.

External source (cited):
  U.S. EIA, "Natural gas-fired electricity conversion efficiency grows as coal remains stable"
  (Today in Energy, 27 Jan 2016), https://www.eia.gov/todayinenergy/detail.php?id=32572
  - US fleet-average heat rate, 2006-2015 (EIA-923/860 generator-level data):
      Natural gas-fired generation:  8,471 -> ~7,878 Btu/kWh  (-7% over the 9-year period)
      Coal-fired generation:         ~10,251 -> ~10,351 Btu/kWh (+1%, "remained stable")
  - Driven substantially by combined-cycle's rising share of gas generation (75% in 2006 ->
    85% in 2015) displacing older/simple-cycle units, not purely per-unit engineering upgrades.

Derivation (this script's own arithmetic, not an EIA-stated annual rate):
  compound annual gas heat-rate improvement = (1 - 0.07)^(1/9) - 1 = -0.803%/yr (heat rate
  falling, i.e. efficiency rising). Applied only to the "Natural gas" MBIE commodity (MBIE's
  Electricity generation use / GHG sheets carry no CCGT/OCGT/cogen sub-split, so "Natural gas"
  is the finest grain available and the single rate applies to NZ's whole gas fleet, mirroring
  the US fleet-average basis it was measured on). Coal held flat (0%, not the EIA's +1%
  worsening: this tests an improvement scenario, not a degradation one, and 1% over 9 years is
  noise-scale). Diesel/LPG/Fuel oil: no cited fleet trend was found (thin literature; NZ's
  diesel/LPG peakers are low-utilisation reserve plant, not represented in the EIA CCGT/coal
  dataset), so they are held flat and left untested rather than assumed.

Caveat: extrapolating a 2006-2015 US fleet trend forward to 2050 (35 years beyond the
observed window, a different country and fleet) is a real methodological stretch. The script
does not claim NZ's gas fleet will improve at this rate; it sizes the effect if it did, as a
standalone sensitivity like the geothermal test (see edgs_common.py / README).

Method: MBIE's generation (GWh, mbie_gwh in edgs_thermal_intensity.parquet) is held exactly
as published; this sensitivity does not touch generation, dispatch, or demand. Only the fuel
input needed to produce that same MBIE generation is scaled down by the cumulative efficiency
factor for "Natural gas" rows (fuel_use_pj' = fuel_use_pj x factor(year)); combustion CO2 is
then recomputed as fuel_use_pj' x MfE factor, the same MfE constant the pipeline uses. This
isolates the efficiency lever only; updates to the MfE factors are out of scope here.

Standalone: reads only edgs_thermal_intensity.parquet (pipeline output), writes only new CSVs.

Outputs (output/edgs/):
  edgs_efficiency_sensitivity.csv          per scenario/year/fuel: baseline vs efficiency-
                                            adjusted fuel_use_pj, combustion_co2_kt, delta
  edgs_efficiency_sensitivity_summary.csv  per scenario/year: national combustion CO2 delta
                                            (Mt, %) and implied generation-EF delta (kg/kWh)
"""
import numpy as np
import pandas as pd

from edgs_common import OUT_DIR, SCENARIOS, MFE_FUEL_EF_KG_PER_GJ, log_factory

log, lines = log_factory()

EIA_SOURCE = ("U.S. EIA, 'Natural gas-fired electricity conversion efficiency grows as coal "
              "remains stable', Today in Energy, 27 Jan 2016 "
              "(https://www.eia.gov/todayinenergy/detail.php?id=32572) - "
              "US fleet heat rate 2006-2015: natural gas -7%, coal +1% ('stable')")
BASE_YEAR = 2024
GAS_ANNUAL_IMPROVEMENT = 1 - (1 - 0.07) ** (1 / 9)  # 0.00803 -> heat rate shrinks 0.803%/yr
EFFICIENCY_RATE_BY_FUEL = {
    "Natural gas": GAS_ANNUAL_IMPROVEMENT,
    "Coal": 0.0,     # EIA found coal essentially flat (+1%/9yr, noise-scale) - held at 0, not applied
    "Diesel": 0.0,   # no cited fleet trend found for NZ-scale diesel peakers - flat, untested
    "LPG": 0.0,      # no cited fleet trend found - flat, untested
    "Fuel oil": 0.0, # no cited fleet trend found - flat, untested
}
log(f"Source: {EIA_SOURCE}")
log(f"Derived compound annual gas heat-rate improvement: {GAS_ANNUAL_IMPROVEMENT*100:.3f}%/yr "
    f"(applied {BASE_YEAR}->2050, cumulative {1-(1-GAS_ANNUAL_IMPROVEMENT)**(2050-BASE_YEAR):.1%} "
    f"by 2050)")

# Load the baseline (reconciled thermal fuel/CO2, per scenario-year-fuel)
recon = pd.read_parquet(OUT_DIR / "edgs_thermal_intensity.parquet")
# Combustion-only rows (exclude the Wood non-CO2 row: efficiency has no meaning for a
# fixed non-biogenic CH4+N2O factor untouched by this sensitivity)
base = recon[recon["flag"] == "MBIE_fueluse_x_MfE"].copy()
MFE_EF = {k: v[0] for k, v in MFE_FUEL_EF_KG_PER_GJ.items()}

# Apply cumulative efficiency factor to fuel input; recompute CO2 from the same MfE
# constant the pipeline uses. Generation (mbie_gwh) is untouched throughout.
def efficiency_factor(fuel, year):
    rate = EFFICIENCY_RATE_BY_FUEL.get(fuel, 0.0)
    yrs = max(0, year - BASE_YEAR)
    return (1 - rate) ** yrs

base["efficiency_factor"] = [efficiency_factor(f, y) for f, y in zip(base["fuel"], base["year"])]
base["fuel_use_pj_efficient"] = base["fuel_use_pj"] * base["efficiency_factor"]
base["mfe_ef_kg_per_gj"] = base["fuel"].map(MFE_EF)
base["combustion_co2_kt_efficient"] = base["fuel_use_pj_efficient"] * 1e6 * base["mfe_ef_kg_per_gj"] / 1e6
base["co2_delta_kt"] = base["combustion_co2_kt_efficient"] - base["combustion_co2_kt"]
base["implied_ef_kg_per_mwh_efficient"] = np.where(
    base["mbie_gwh"] > 0, base["combustion_co2_kt_efficient"] * 1e6 / (base["mbie_gwh"] * 1000.0), np.nan)

detail_cols = ["scenario", "year", "fuel", "mbie_gwh", "fuel_use_pj", "fuel_use_pj_efficient",
               "efficiency_factor", "combustion_co2_kt", "combustion_co2_kt_efficient",
               "co2_delta_kt", "implied_ef_kg_per_mwh", "implied_ef_kg_per_mwh_efficient"]
detail = base[detail_cols].sort_values(["scenario", "year", "fuel"])
detail.to_csv(OUT_DIR / "edgs_efficiency_sensitivity.csv", index=False)
log(f"\nWrote edgs_efficiency_sensitivity.csv ({len(detail):,} rows)")

# National summary: combustion CO2 delta per scenario-year (Mt, %) + implied
# generation-side EF delta (using the same MBIE net-generation denominator the
# pipeline's generation EF uses, i.e. total generation is unaffected).
targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
netgen = (targets[targets["metric"] == "net_generation"]
          .groupby(["scenario", "year"])["value"].sum().rename("netgen_gwh"))  # GWh, all commodities

nat = base.groupby(["scenario", "year"]).agg(
    baseline_co2_kt=("combustion_co2_kt", "sum"),
    efficient_co2_kt=("combustion_co2_kt_efficient", "sum"),
).reset_index()
nat["co2_delta_kt"] = nat["efficient_co2_kt"] - nat["baseline_co2_kt"]
nat["co2_delta_pct"] = np.where(nat["baseline_co2_kt"] > 0,
                                 nat["co2_delta_kt"] / nat["baseline_co2_kt"] * 100, np.nan)
nat = nat.merge(netgen.reset_index(), on=["scenario", "year"], how="left")
nat["baseline_ef_kg_per_kwh"] = nat["baseline_co2_kt"] * 1e6 / (nat["netgen_gwh"] * 1e6)
nat["efficient_ef_kg_per_kwh"] = nat["efficient_co2_kt"] * 1e6 / (nat["netgen_gwh"] * 1e6)
nat["ef_delta_kg_per_kwh"] = nat["efficient_ef_kg_per_kwh"] - nat["baseline_ef_kg_per_kwh"]
nat = nat.sort_values(["scenario", "year"])
nat.to_csv(OUT_DIR / "edgs_efficiency_sensitivity_summary.csv", index=False)
log(f"Wrote edgs_efficiency_sensitivity_summary.csv ({len(nat):,} scenario-year rows)")

# Report
log("\nNational combustion CO2 delta against the pipeline baseline, by scenario, selected years:")
for scenario in SCENARIOS:
    s = nat[nat["scenario"] == scenario].set_index("year")
    parts = []
    for yr in (2024, 2030, 2040, 2050):
        if yr in s.index:
            parts.append(f"{yr}: {s.loc[yr,'co2_delta_pct']:+.2f}% "
                         f"({s.loc[yr,'co2_delta_kt']:+.1f} kt)")
    log(f"  {scenario}: " + " | ".join(parts))

log(f"\n2050 EF delta (efficiency-adjusted minus baseline), by scenario:")
for scenario in SCENARIOS:
    row = nat[(nat["scenario"] == scenario) & (nat["year"] == 2050)]
    if len(row):
        r = row.iloc[0]
        log(f"  {scenario}: baseline {r.baseline_ef_kg_per_kwh:.5f} -> "
            f"efficient {r.efficient_ef_kg_per_kwh:.5f} kg/kWh "
            f"({r.ef_delta_kg_per_kwh:+.5f}, national-generation basis)")

overall_2050 = nat[nat["year"] == 2050]
log(f"\n2050 across-scenario combustion CO2 delta range: "
    f"{overall_2050['co2_delta_pct'].min():.2f}% to {overall_2050['co2_delta_pct'].max():.2f}%")

(OUT_DIR / "processing_log_efficiency_sensitivity.txt").write_text("\n".join(lines), encoding="utf-8")
log("\nNot adopted in the pipeline: standalone sensitivity only (see docstring).")
