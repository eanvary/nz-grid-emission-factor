"""
Extends Category D1 (MBIE cross-check) to 2024 Q1 to 2026 Q1 (the latest quarter in
MBIE's published workbook), using the 8 raw months for Jan-Aug 2026 downloaded from the
Electricity Authority's public EMI portal. Same method as the D1 check (full scope, no
autoproducer exclusion, national total CO2 / national total generation per quarter);
only the window differs.

2024-2025 months: read from the released output/monthly_emission_factor_NI_SI.csv
(NI+SI summed to national), which is already validated.
2026 months (Jan-Aug): computed here from the 2026 raw files, using the
pipeline's own generation reader, POC->island map and fuel/factor attribution
(generation_pipeline/fuel_attribution.py: FuelAttribution.generation / .attribute,
poc_island_map), so 2026 is on the same basis as the released 2024-2025 months.
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import FuelAttribution, poc_island_map  # noqa: E402

MBIE_PATH = ROOT / "generation_pipeline" / "MBIE_Quarterly_Electricity_Emissions_2026Q1.xlsx"

NEW_MONTHS = ["202601", "202602", "202603", "202604", "202605", "202606", "202607", "202608"]

# National monthly CO2/generation for the 8 new 2026 months (full scope,
# matching D1's own method exactly -- no autoproducer exclusion).
poc_island = poc_island_map()
fa = FuelAttribution()

print(f"Computing national monthly EF for {len(NEW_MONTHS)} new 2026 months (full scope, matches D1 method)...")
gen = fa.generation(level="month", include_fills=True, months=NEW_MONTHS)
gen["island"] = gen["poc"].map(poc_island)
gen = gen[gen["island"].isin(["NI", "SI"])]  # matches D1: EA/EMI POCs with a known island
gen = fa.attribute(gen)
parts = [gen.groupby(["year", "month"]).agg(gen=("gen_mwh", "sum"), co2=("co2_kg", "sum")).reset_index()]

new_monthly = pd.concat(parts, ignore_index=True)
print(new_monthly.to_string(index=False))

# 2024-2025 months from the released, validated output.
released = pd.read_csv(ROOT / "output" / "monthly_emission_factor_NI_SI.csv")
released_national = released.groupby(["year", "month"]).agg(
    gen=("total_gen_MWh", "sum"), co2=("total_CO2_kg", "sum")
).reset_index()
released_2024_2025 = released_national[released_national.year.isin([2024, 2025])]

nat = pd.concat([released_2024_2025, new_monthly], ignore_index=True).sort_values(["year", "month"])
nat["period"] = pd.to_datetime(nat[["year", "month"]].assign(day=1))
nat["quarter"] = nat["period"].dt.to_period("Q")
qmap = {1: "Mar", 2: "Jun", 3: "Sep", 4: "Dec"}
qagg = nat.groupby("quarter").agg(gen=("gen", "sum"), co2=("co2", "sum")).reset_index()
qagg["qlabel"] = qagg["quarter"].apply(lambda p: f"{qmap[p.quarter]} {str(p.year)[2:]}")
qagg["ours_kg_per_mwh"] = qagg["co2"] / qagg["gen"]

# MBIE's own published figures for the same quarters.
xl = pd.ExcelFile(MBIE_PATH)
dfm = xl.parse("Electricity EFs", header=None)
q_labels = dfm.iloc[8, 1:].tolist()
co2c, ch4c, n2oc = dfm.iloc[10, 1:].tolist(), dfm.iloc[11, 1:].tolist(), dfm.iloc[12, 1:].tolist()
mb = pd.DataFrame({"qlabel": q_labels, "co2": co2c, "ch4": ch4c, "n2o": n2oc}).dropna(subset=["qlabel"])
mb["mbie_kg_per_mwh"] = mb["co2"] + mb["ch4"] * 28 + mb["n2o"] * 265  # same units as D1's own script -- no scaling applied there either

comp = qagg.merge(mb, on="qlabel", how="inner").sort_values("quarter")
comp["diff_pct"] = (comp["ours_kg_per_mwh"] - comp["mbie_kg_per_mwh"]) / comp["mbie_kg_per_mwh"] * 100

r = comp["ours_kg_per_mwh"].corr(comp["mbie_kg_per_mwh"])
mad = comp["diff_pct"].abs().mean()

print(f"\n=== 2024 Q1 -- 2026 Q1 comparison (n={len(comp)} quarters) ===")
print(comp[["qlabel", "ours_kg_per_mwh", "mbie_kg_per_mwh", "diff_pct"]].round(2).to_string(index=False))
print(f"\nPearson r = {r:.4f}")
print(f"Mean |diff| = {mad:.2f}%")

comp.to_csv(HERE / "mbie_2024_2026_comparison.csv", index=False)
print(f"\nWrote mbie_2024_2026_comparison.csv")
