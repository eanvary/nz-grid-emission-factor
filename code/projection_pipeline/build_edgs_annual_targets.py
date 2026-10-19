"""
Module 1: Step 1: extract MBIE annual national targets (direct transcription;
no assumption). Every value here is source_tag = MBIE_annual_disaggregated.

For each scenario x year (2024-2050):
  - annual total demand (TWh)              <- Results 'Total electricity demand'
  - annual peak demand (GW)                <- Results 'Peak demand'
  - annual net generation by fuel (GWh)    <- Results 'Electricity generation',
                                              Variable = Net electricity generation
  - annual national avg EF (kg CO2-e/kWh)  <- Results 'Emission factors' (cross-check)

Outputs (output/edgs/):
  edgs_annual_targets.parquet   long: scenario, year, metric, commodity, value, unit, source_detail
  edgs_annual_targets.csv       same (readable)
"""
import pandas as pd

from edgs_common import RESULTS_XLSX, OUT_DIR, SCENARIOS, YEARS, COMMODITY, log_factory

log, lines = log_factory()
YMIN, YMAX = YEARS[0], YEARS[-1]


def read_sheet(name):
    return pd.read_excel(RESULTS_XLSX, sheet_name=name)


# 1a. Total electricity demand (TWh)
dem = read_sheet("Total electricity demand")
dem = dem[(dem["TimePeriod"].between(YMIN, YMAX)) & (dem["Scenario"].isin(SCENARIOS))]
dem_rows = pd.DataFrame({
    "scenario": dem["Scenario"], "year": dem["TimePeriod"],
    "metric": "annual_demand", "commodity": "", "value": dem["Value"],
    "unit": dem["Unit"], "source_detail": "Results!Total electricity demand.Value",
})
log(f"Total electricity demand: {len(dem_rows)} rows "
    f"({dem_rows['value'].min():.1f}-{dem_rows['value'].max():.1f} TWh)")

# 1b. Peak demand (GW): Variable 'New Zealand peak load'
pk = read_sheet("Peak demand")
pk = pk[(pk["TimePeriod"].between(YMIN, YMAX)) & (pk["Scenario"].isin(SCENARIOS))
        & (pk["Variable"] == "New Zealand peak load")]
pk_rows = pd.DataFrame({
    "scenario": pk["Scenario"], "year": pk["TimePeriod"],
    "metric": "annual_peak", "commodity": "", "value": pk["Value"],
    "unit": pk["Unit"], "source_detail": "Results!Peak demand.Value[New Zealand peak load]",
})
log(f"Peak demand: {len(pk_rows)} rows ({pk_rows['value'].min():.2f}-{pk_rows['value'].max():.2f} GW)")

# 1c. Net electricity generation by fuel (GWh)
gen = read_sheet("Electricity generation")
gen = gen[(gen["TimePeriod"].between(YMIN, YMAX)) & (gen["Scenario"].isin(SCENARIOS))
          & (gen["Variable"] == "Net electricity generation")]
unknown = sorted(set(gen["Commodity"]) - set(COMMODITY))
if unknown:
    log(f"WARNING — commodities in sheet not in crosswalk: {unknown}")
gen_rows = pd.DataFrame({
    "scenario": gen["Scenario"], "year": gen["TimePeriod"],
    "metric": "net_generation", "commodity": gen["Commodity"], "value": gen["Value"],
    "unit": gen["Unit"], "source_detail": "Results!Electricity generation.Value[Net electricity generation]",
})
log(f"Net generation by fuel: {len(gen_rows)} rows, unit(s)={sorted(gen['Unit'].unique())}")
# National annual total generation (all fuels) for sanity
nat = gen_rows.groupby(["scenario", "year"])["value"].sum().reset_index()
log(f"  National annual generation range: {nat['value'].min()/1000:.1f}-{nat['value'].max()/1000:.1f} TWh")

# 1d. Emission factors (kg CO2-e/kWh): national grid average, cross-check
ef = read_sheet("Emission factors")
ef = ef[(ef["TimePeriod"].between(YMIN, YMAX)) & (ef["Scenario"].isin(SCENARIOS))]
ef_rows = pd.DataFrame({
    "scenario": ef["Scenario"], "year": ef["TimePeriod"],
    "metric": "grid_emission_factor", "commodity": "", "value": ef["Value"],
    "unit": ef["Unit"], "source_detail": "Results!Emission factors.Value",
})
log(f"Emission factors: {len(ef_rows)} rows "
    f"({ef_rows['value'].min():.4f}-{ef_rows['value'].max():.4f} kg CO2-e/kWh)")

# Combine + write
out = pd.concat([dem_rows, pk_rows, gen_rows, ef_rows], ignore_index=True)
out["source_tag"] = "MBIE_annual_disaggregated"
out = out[["scenario", "year", "metric", "commodity", "value", "unit",
           "source_tag", "source_detail"]].sort_values(
    ["scenario", "year", "metric", "commodity"]).reset_index(drop=True)

# Completeness check: every scenario x year must have demand, peak, EF, and >=1 fuel row
grid = out.groupby(["scenario", "year"])["metric"].agg(set)
missing = []
for (sc, yr), mets in grid.items():
    for req in ("annual_demand", "annual_peak", "grid_emission_factor", "net_generation"):
        if req not in mets:
            missing.append((sc, yr, req))
if missing:
    log(f"WARNING — missing metrics: {missing[:20]}")
else:
    log(f"OK — all {len(SCENARIOS)} scenarios x {len(YEARS)} years complete for all 4 metrics")

out.to_parquet(OUT_DIR / "edgs_annual_targets.parquet", index=False)
out.to_csv(OUT_DIR / "edgs_annual_targets.csv", index=False)
log(f"\nWrote edgs_annual_targets.parquet / .csv ({len(out):,} rows)")
(OUT_DIR / "processing_log_annual_targets.txt").write_text("\n".join(lines), encoding="utf-8")
