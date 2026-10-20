"""
Module 3: short-run marginal cost per thermal plant, per year, and the
resulting merit order (thermal plants ranked ascending by marginal cost).

Marginal_cost (NZD/MWh) =
      Heat Rate [GJ/GWh] x Fuel delivery cost [NZD/GJ] / 1000       (fuel cost)
    + Variable operating cost [NZD/MWh]                             (var O&M)
    + Fuel EF [kg CO2-e/GJ] x Heat Rate [GJ/GWh] / 1000            (carbon cost)
        x Carbon price [NZD/tonne] / 1000

  Fuel EF: MfE ME1829 (edgs_common.MFE_FUEL_EF_KG_PER_GJ)  [external, cited]
  Carbon price: Assumptions 'Commodity prices'[Effective carbon price]
                Dollars per t CO2, by scenario x year.
  Renewables (dispatch_class == renewable) are must-run (Module 4), not ranked here.

source_tag = calculated (formula over MBIE Generation Stack + MBIE carbon price + MfE EF)

Output: output/edgs/edgs_merit_order.parquet
  scenario, year, plant, commodity, island, capacity_mw, marginal_cost_nzd_per_mwh,
  fuel_cost, var_om, carbon_cost, carbon_price_nzd_per_t, merit_rank, source_detail
"""
import numpy as np
import pandas as pd

from edgs_common import (ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, 
                         fuel_ef_kg_per_gj, MFE_SOURCE, log_factory)

log, lines = log_factory()

reg = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")
thermal = reg[reg["dispatch_class"] == "thermal"].copy()
log(f"Thermal plant-year rows: {len(thermal):,}")

# Effective carbon price by scenario x year (NZD/tonne CO2)
cp = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Commodity prices")
cp = cp[(cp["Variable"] == "Effective carbon price") & (cp["Scenario"].isin(SCENARIOS))]
carbon = cp.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()

# Marginal cost
thermal["fuel_ef_kg_per_gj"] = thermal["commodity"].map(fuel_ef_kg_per_gj)
missing_ef = sorted(thermal.loc[thermal["fuel_ef_kg_per_gj"] == 0, "commodity"].unique())
if missing_ef:
    log(f"NOTE: thermal commodities with 0 fuel EF (check): {missing_ef}")

thermal["carbon_price_nzd_per_t"] = [
    carbon.get((sc, yr), np.nan) for sc, yr in zip(thermal["scenario"], thermal["year"])
]
if thermal["carbon_price_nzd_per_t"].isna().any():
    log(f"WARNING: {thermal['carbon_price_nzd_per_t'].isna().sum()} rows missing carbon price")

hr = thermal["heat_rate_gj_per_gwh"]
thermal["fuel_cost"] = hr * thermal["fuel_delivery_nzd_per_gj"] / 1000.0
thermal["var_om"] = thermal["var_om_nzd_per_mwh"]
thermal["carbon_cost"] = (thermal["fuel_ef_kg_per_gj"] * hr / 1000.0
                          * thermal["carbon_price_nzd_per_t"] / 1000.0)
thermal["marginal_cost_nzd_per_mwh"] = (
    thermal["fuel_cost"].fillna(0) + thermal["var_om"].fillna(0) + thermal["carbon_cost"].fillna(0)
)

# Merit rank within scenario x year (ascending marginal cost, cheapest first)
thermal["merit_rank"] = (
    thermal.groupby(["scenario", "year"])["marginal_cost_nzd_per_mwh"]
    .rank(method="first").astype(int)
)
thermal["source_detail"] = (
    "calculated: merit-order cost formula; Fuel EF=" + MFE_SOURCE
    + "; carbon=Assumptions!Commodity prices[Effective carbon price]"
)

# Sanity: cheapest and dearest thermal in Reference across years
log("\nReference merit order: cheapest and dearest thermal, selected years:")
for yr in (2024, 2035, 2050):
    s = thermal[(thermal["scenario"] == "Reference") & (thermal["year"] == yr)]
    s = s.sort_values("marginal_cost_nzd_per_mwh")
    if len(s):
        lo, hi = s.iloc[0], s.iloc[-1]
        log(f"  {yr}: cheapest {lo['plant'][:32]:32s} ${lo['marginal_cost_nzd_per_mwh']:6.1f}/MWh "
            f"| dearest {hi['plant'][:28]:28s} ${hi['marginal_cost_nzd_per_mwh']:7.1f}/MWh "
            f"(carbon ${lo['carbon_price_nzd_per_t']:.0f}/t)")

# The coal-gas ordering flips as the carbon price changes: report where coal leaves the money
ref = thermal[thermal["scenario"] == "Reference"]
for yr in (2024, 2050):
    s = ref[ref["year"] == yr]
    coal = s[s["commodity"] == "Coal"]["marginal_cost_nzd_per_mwh"]
    gas = s[s["commodity"] == "Natural gas"]["marginal_cost_nzd_per_mwh"]
    if len(coal) and len(gas):
        log(f"  {yr}: coal ${coal.mean():.1f}/MWh, gas ${gas.mean():.1f}/MWh (mean)")

out = thermal[["scenario", "year", "plant", "commodity", "island", "capacity_mw",
               "marginal_cost_nzd_per_mwh", "fuel_cost", "var_om", "carbon_cost",
               "carbon_price_nzd_per_t", "merit_rank", "source_detail"]]
out.to_parquet(OUT_DIR / "edgs_merit_order.parquet", index=False)
log(f"\nWrote edgs_merit_order.parquet ({len(out):,} rows)")
(OUT_DIR / "processing_log_merit_order.txt").write_text("\n".join(lines), encoding="utf-8")
