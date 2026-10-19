"""
Phase 1: spatial structure.
NI vs SI EF gap over time (generation-side and consumption-side); the
consumption-side vs generation-side wedge per island (Cook Strait reallocation
effect); hours where consumption and generation EF diverge most.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGS = ROOT / "output" / "edgs"
TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

ef = pd.read_parquet(EDGS / "edgs_hourly_emission_factor.parquet")
ef["year"] = ef["datetime_hour"].dt.year

gen = pd.read_parquet(EDGS / "edgs_hourly_generation.parquet")
gen_isl = gen.groupby(["scenario", "island", "datetime_hour"], observed=True)["generation_mwh"].sum().reset_index()

def wmean(g, wcol="generation_mwh"):
    w = g[wcol].fillna(0)
    if w.sum() == 0:
        return np.nan
    return np.average(g["emission_factor_kg_co2e_per_kwh"], weights=w)

# NI vs SI gap over time, both bases
log("=== NI vs SI annual generation-weighted EF gap, by basis, all scenarios ===")
ni_si = ef[ef["island"].isin(["NI", "SI"])].merge(gen_isl, on=["scenario", "island", "datetime_hour"], how="left")
annual_isl = (ni_si.groupby(["scenario", "island", "ef_basis", "year"])
              .apply(lambda g: pd.Series({"ef": wmean(g)}), include_groups=False).reset_index())
annual_isl.to_csv(TABLES / "phase1_spatial_annual_by_island.csv", index=False)

gap = annual_isl.pivot_table(index=["scenario", "ef_basis", "year"], columns="island", values="ef").reset_index()
gap["NI_minus_SI"] = gap["NI"] - gap["SI"]
gap["NI_SI_ratio"] = gap["NI"] / gap["SI"].replace(0, np.nan)
gap.to_csv(TABLES / "phase1_ni_si_gap.csv", index=False)
log(gap[(gap["scenario"] == "Reference")].to_string(index=False))

log("\nNOTE: SI generation-side EF is ~0 (no thermal fleet, confirmed Phase 0) for all "
    "years -- so the NI-SI gap on the GENERATION side is essentially NI's own EF level. "
    "The CONSUMPTION side is where the gap is genuinely informative (SI consumption EF "
    "> 0 whenever it imports NI's dirtier power over the HVDC).")

# Consumption vs generation wedge, per island
log("\n=== Consumption-side minus generation-side EF wedge, per island, over time ===")
wedge_rows = []
for isl in ["NI", "SI"]:
    g_g = annual_isl[(annual_isl["island"] == isl) & (annual_isl["ef_basis"] == "generation")]
    g_c = annual_isl[(annual_isl["island"] == isl) & (annual_isl["ef_basis"] == "consumption")]
    m = g_g.merge(g_c, on=["scenario", "year"], suffixes=("_gen", "_cons"))
    m["island"] = isl
    m["wedge"] = m["ef_cons"] - m["ef_gen"]
    m["wedge_pct_of_gen"] = 100 * m["wedge"] / m["ef_gen"]
    wedge_rows.append(m)
wedge_df = pd.concat(wedge_rows, ignore_index=True)
wedge_df.to_csv(TABLES / "phase1_consumption_generation_wedge.csv", index=False)
log(wedge_df[wedge_df["scenario"] == "Reference"][["island", "year", "ef_gen", "ef_cons", "wedge", "wedge_pct_of_gen"]].to_string(index=False))

# National consumption EF trajectory (blended; published on the consumption basis only)
log("\n=== National (consumption-basis, blended) annual EF vs NI/SI consumption EF, Reference ===")
nat = ef[ef["island"] == "National"].merge(
    gen.groupby(["scenario", "datetime_hour"], observed=True)["generation_mwh"].sum().reset_index(),
    on=["scenario", "datetime_hour"], how="left")
nat_annual = (nat.groupby(["scenario", "year"])
              .apply(lambda g: pd.Series({"national_cons_ef": wmean(g)}), include_groups=False).reset_index())
nat_annual.to_csv(TABLES / "phase1_national_consumption_trajectory.csv", index=False)
log(nat_annual[nat_annual["scenario"] == "Reference"].head(10).to_string(index=False))

# Hours of max NI consumption-vs-generation divergence: characterise them
log("\n=== Characterising the hours of largest NI consumption-vs-generation EF divergence (Reference, 2035) ===")
ef_ni_2035 = ef[(ef["scenario"] == "Reference") & (ef["island"] == "NI") & (ef["year"] == 2035)]
piv = ef_ni_2035.pivot_table(index="datetime_hour", columns="ef_basis", values="emission_factor_kg_co2e_per_kwh")
piv["divergence"] = piv["consumption"] - piv["generation"]
piv["hour"] = piv.index.hour
piv["month"] = piv.index.month
top20 = piv.reindex(piv["divergence"].abs().sort_values(ascending=False).index).head(20)
log(top20.to_string())
log("\nHour-of-day distribution of the top 200 most-divergent hours:")
top200 = piv.reindex(piv["divergence"].abs().sort_values(ascending=False).index).head(200)
log(top200["hour"].value_counts().sort_index().to_string())
log("\nMonth distribution of the top 200 most-divergent hours:")
log(top200["month"].value_counts().sort_index().to_string())
piv.to_csv(TABLES / "phase1_ni_divergence_hours_2035.csv")

with open(LOGS / "phase1_spatial_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("\nDone.")
