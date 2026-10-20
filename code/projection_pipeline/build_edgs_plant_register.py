"""
Module 2: plant register + commissioning/retirement calendar.

From Generation Stack (all plants, existing + generic future) build, per scenario
x year 2024-2050, the set of active plants with island, capacity, commodity (from Tech)
and (thermal only) heat rate / variable O&M / fuel-delivery cost. Retirement dates
come from the EDGS 2024 report, Appendix One. New-build island tags are
cross-checked against the GEM build schedule.

source_tag:
  plant attributes:                     MBIE_annual_disaggregated (Generation Stack)
  active-year / retirement / biomass:   calculated (deterministic from Generation Stack and retirement calendar)

Outputs (output/edgs/):
  edgs_plant_register.parquet   long: scenario, year, plant, commodity, dispatch_class,
                                       island, capacity_mw, heat_rate_gj_per_gwh,
                                       var_om_nzd_per_mwh, fuel_delivery_nzd_per_gj,
                                       status, source_detail
  edgs_gem_build.parquet        GEM build schedule (island-tagged new-build capacity)
"""
import numpy as np
import pandas as pd

from edgs_common import (RESULTS_XLSX, ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS,
                         REGION_TO_ISLAND, TECH_TO_COMMODITY, COMMODITY,
                         retirement_rules, log_factory)

log, lines = log_factory()
YMIN, YMAX = YEARS[0], YEARS[-1]

gs_all = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Generation Stack")
gem = pd.read_excel(RESULTS_XLSX, sheet_name="GEM build schedule")


# Retirement matcher (EDGS 2024 report, Appendix One)
def match_retirement(plant_name, rules):
    """First year the plant is no longer available in a scenario (np.inf if never)."""
    p = plant_name.lower()
    if "taranaki combined cycle" in p:
        return rules.get("Taranaki Combined Cycle", np.inf) + 1  # 'end of 2024', so gone from 2025
    if "huntly unit 5" in p:
        return rules.get("Huntly Unit 5", np.inf) + 1
    if "stratford peaker" in p:
        return rules.get("Stratford peaker", np.inf) + 1
    if ("huntly unit 1" in p or "huntly unit 2" in p) and "wood" not in p:
        # The Generation Stack lists the converted Rankine units as separate Wood plants from the
        # conversion year, so the coal and gas entries retire then instead of being converted.
        conv = rules.get("Huntly Rankine")  # ('biomass', 2032) in Innovation and Environmental
        return conv[1] if conv else np.inf
    return np.inf


# Build per-scenario, per-year active plant register
records = []
si_thermal_report = {}

for scenario in SCENARIOS:
    gs = gs_all[gs_all["Scenario"] == scenario].copy()
    rules = retirement_rules(scenario)

    # commissioning year: Fixed if present, else Earliest, else already-active (Current)
    comm = gs["Fixed Commissioning Year"].fillna(gs["Earliest Commissioning Year"])
    gs["commission_year"] = comm.fillna(YMIN).astype(int)

    unknown_tech = sorted(set(gs["Tech"]) - set(TECH_TO_COMMODITY))
    if unknown_tech:
        log(f"WARNING [{scenario}]: Tech not in crosswalk: {unknown_tech}")

    for _, row in gs.iterrows():
        commodity = TECH_TO_COMMODITY.get(row["Tech"])
        if commodity is None:
            continue
        island = REGION_TO_ISLAND.get(row["Region"])
        if island is None:
            log(f"WARNING [{scenario}]: region '{row['Region']}' not mapped ({row['Plant']})")
            continue
        retire_year = match_retirement(row["Plant"], rules)
        cap = float(row["Capacity (MW)"]) if pd.notna(row["Capacity (MW)"]) else 0.0

        for yr in YEARS:
            if yr < row["commission_year"] or yr >= retire_year:
                continue
            com, dclass = commodity, COMMODITY[commodity][1]
            src = f"Assumptions!Generation Stack[{row['Status']}]"
            records.append({
                "scenario": scenario, "year": yr, "plant": row["Plant"],
                "commodity": com, "dispatch_class": dclass, "island": island,
                "capacity_mw": cap,
                "heat_rate_gj_per_gwh": float(row["Heat Rate (GJ/GWh)"]) if pd.notna(row["Heat Rate (GJ/GWh)"]) else np.nan,
                "var_om_nzd_per_mwh": float(row["Variable operating costs (NZD/MWh)"]) if pd.notna(row["Variable operating costs (NZD/MWh)"]) else np.nan,
                "fuel_delivery_nzd_per_gj": float(row["Fuel delivery costs (NZD/GJ)"]) if pd.notna(row["Fuel delivery costs (NZD/GJ)"]) else np.nan,
                "status": row["Status"], "source_detail": src,
            })

reg = pd.DataFrame.from_records(records)
log(f"Plant register: {len(reg):,} scenario-year-plant rows")

# Reports
# SI thermal? (drives whether SI EF can be > 0)
si_thermal = reg[(reg["island"] == "SI") & (reg["dispatch_class"] == "thermal")]
for scenario in SCENARIOS:
    s = si_thermal[si_thermal["scenario"] == scenario]
    cap = s.groupby("year")["capacity_mw"].sum()
    si_thermal_report[scenario] = float(cap.max()) if len(cap) else 0.0
log("\nSI thermal capacity (max MW across years) by scenario:")
for sc, mw in si_thermal_report.items():
    log(f"  {sc}: {mw:.0f} MW" + ("; SI EF can be >0" if mw > 0 else "; SI EF about 0 (all-renewable)"))

# Thermal capacity trajectory (national): sanity check against retirements
log("\nNational thermal capacity (MW) by scenario, selected years:")
for scenario in SCENARIOS:
    s = reg[(reg["scenario"] == scenario) & (reg["dispatch_class"] == "thermal")]
    caps = s.groupby("year")["capacity_mw"].sum()
    log(f"  {scenario}: " + ", ".join(f"{y}:{caps.get(y,0):.0f}" for y in (2024, 2030, 2037, 2050)))

# TCC must be gone by 2025; Huntly U5 gone by 2038 (default) / 2033 (Innov/Env)
tcc_2025 = reg[(reg["year"] == 2025) & (reg["plant"].str.contains("Taranaki Combined Cycle"))]
log(f"\nRetirement check: TCC rows in 2025 (expect 0): {len(tcc_2025)}")
for scenario, yr_gone in [("Reference", 2038), ("Innovation", 2033)]:
    u5 = reg[(reg["scenario"] == scenario) & (reg["year"] == yr_gone)
             & (reg["plant"].str.contains("Huntly Unit 5"))]
    log(f"Retirement check: {scenario} Huntly U5 rows in {yr_gone} (expect 0): {len(u5)}")

# GEM build schedule (authoritative new-build island tag): normalise + write
gem_out = gem.rename(columns={
    "Commissioning_Year": "year", "Value": "capacity_mw", "Island": "island_full",
    "Technology_Type": "technology_type", "Commodity": "commodity",
    "Scenario": "scenario", "Plant_Name": "plant",
})
gem_out["island"] = gem_out["island_full"].map({"North Island": "NI", "South Island": "SI"})
gem_out = gem_out[gem_out["scenario"].isin(SCENARIOS)]
gem_out = gem_out[["scenario", "year", "commodity", "technology_type", "island",
                   "capacity_mw", "plant"]]
log(f"\nGEM build schedule: {len(gem_out):,} rows; commodities={sorted(gem_out['commodity'].unique())}")

# No battery/BESS capacity figure exists in either workbook. The only
# storage/flexibility line item MBIE publishes is 'Demand side response'
# (GEM build schedule + Results generation). Assumption 2 anchors to that
# MBIE quantity rather than inventing a battery MW figure (which would be a
# forbidden third assumption).
dsr = gem_out[gem_out["commodity"] == "Demand side response"]
log(f"Demand side response new-build in GEM: {len(dsr)} rows, "
    f"cumulative by 2050 (Reference): "
    f"{dsr[dsr.scenario=='Reference']['capacity_mw'].sum():.0f} MW")

reg.to_parquet(OUT_DIR / "edgs_plant_register.parquet", index=False)
gem_out.to_parquet(OUT_DIR / "edgs_gem_build.parquet", index=False)
log(f"\nWrote edgs_plant_register.parquet ({len(reg):,} rows) and edgs_gem_build.parquet ({len(gem_out):,} rows)")
(OUT_DIR / "processing_log_plant_register.txt").write_text("\n".join(lines), encoding="utf-8")
