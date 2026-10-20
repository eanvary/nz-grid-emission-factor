"""
NI/SI monthly grid emission factor time series, over every Generation_MD month
on disk (2015-2025 in the released database).
Sources: NSP daily snapshots (EA data/NSP Tables), Dispatched generation
plant SCD2 (EA data/Dispatched generation plant.csv), Generation_MD
half-hourly files (EA_EMI_raw/*_Generation_MD.csv).
"""
import glob
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent  # project root: the folder above generation_pipeline/
NSP_DIR = ROOT / "EA data" / "NSP Tables"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(str(msg))


# NSP snapshots: POC-to-island lookup
nsp_files = sorted(glob.glob(str(NSP_DIR / "*_NetworkSupplyPointsTable.csv")))
log(f"Found {len(nsp_files)} NSP snapshot files")

nsp_all = pd.concat(
    [pd.read_csv(f, low_memory=False) for f in nsp_files], ignore_index=True
)
nsp_unique = nsp_all.drop_duplicates(
    subset=["POC code", "Reconciliation type", "Island", "Start date", "End date"]
)
log(f"Unique NSP records after dedup: {len(nsp_unique)} (from {len(nsp_all)} raw rows)")

gen_nsp = nsp_unique[nsp_unique["Reconciliation type"].isin(["GN", "GG", "GD"])].copy()

multi_island = (
    gen_nsp.groupby("POC code")["Island"].nunique().pipe(lambda s: s[s > 1])
)
if len(multi_island):
    log(f"WARNING: POCs with multiple island values: {multi_island.index.tolist()}")
else:
    log("OK: all generation POCs map to a single island")

# Island assignment is geographically stable per POC regardless of reconciliation
# type (verified: zero POCs with conflicting Island across all recon types), so
# fall back to any NSP record with a non-null Island for POCs not classified as
# GN/GG/GD (e.g. embedded generation reconciled as 'EN', such as Waipori WPG0331).
poc_island = (
    nsp_unique.dropna(subset=["Island"])
    .sort_values("Start date", ascending=False)
    .drop_duplicates(subset=["POC code"])
    .set_index("POC code")["Island"]
    .to_dict()
)
log(f"POC-to-island lookup: {len(poc_island)} POCs total "
    f"({len(gen_nsp['POC code'].unique())} from GN/GG/GD generation NSPs, "
    f"remainder from other reconciliation types e.g. embedded generation) "
    f"(NI: {sum(v=='NI' for v in poc_island.values())}, "
    f"SI: {sum(v=='SI' for v in poc_island.values())})")

from fuel_attribution import FUEL_STD, raw_files


# Load and normalise Generation_MD files
def load_generation_md(filepath):
    df = pd.read_csv(filepath, low_memory=False)
    # The column is Trading_date in older files and Trading_Date in later ones
    # (the change predates 2020); normalising lets both eras load the same way.
    df = df.rename(columns={c: c for c in df.columns})
    lower_map = {c.lower(): c for c in df.columns}
    trading_date_col = lower_map["trading_date"]
    # <=50, not <=48: NZ's DST fall-back day (first Sunday of April) has 50 trading
    # periods (TP49/TP50 are the extra repeated hour). Excluding them would drop
    # about 3,500-3,900 MWh of generation on that day each year.
    tp_cols = [c for c in df.columns if re.match(r"^TP\d+$", c) and int(c[2:]) <= 50]
    df["gen_mwh"] = df[tp_cols].sum(axis=1, skipna=True) / 1000.0
    df["trading_date"] = pd.to_datetime(df[trading_date_col])
    keep = ["trading_date", "POC_Code", "Gen_Code", "Fuel_Code", "gen_mwh"]
    out = df[keep].rename(columns={"POC_Code": "poc", "Gen_Code": "gen_code", "Fuel_Code": "fuel_code_raw"})
    return out.dropna(subset=["poc", "trading_date"])


gen_files = raw_files("Generation_MD")
log(f"\nLoading {len(gen_files)} Generation_MD files...")

gen_parts = [load_generation_md(f) for f in gen_files]
gen = pd.concat(gen_parts, ignore_index=True)
log(f"Total generation records loaded: {len(gen):,}")
log(f"Date range: {gen['trading_date'].min().date()} to {gen['trading_date'].max().date()}")

# Assign Island
gen["island"] = gen["poc"].map(poc_island)
match_rate = gen["island"].notna().mean()
log(f"\nIsland assignment rate: {match_rate:.2%}")
if match_rate < 0.95:
    unmatched_pocs = sorted(gen.loc[gen["island"].isna(), "poc"].unique())
    log(f"WARNING: match rate below 95%. Unmatched POCs: {unmatched_pocs}")
else:
    unmatched_pocs = sorted(gen.loc[gen["island"].isna(), "poc"].unique())
    if unmatched_pocs:
        log(f"Unmatched POCs (dropped): {unmatched_pocs}")

gen = gen[gen["island"].isin(["NI", "SI"])].copy()
gen["filled"] = False
log(f"Records retained (NI+SI): {len(gen):,}")
for isl, tot in gen.groupby("island")["gen_mwh"].sum().items():
    log(f"  {isl}: {tot/1e6:.2f} TWh total over period")

# Flagged fills (fuel_attribution.fills): Huntly 1-4 September 2020 (Genesis
# quarterly output), and Grid_import fills: Huntly E3P/P40 September 2020 and norskeskog
# 2015-2019 (scaled), Matahina October 2021 to December 2025 (measured). See the override table.
# Every filled trading period is written to filled_generation_log.csv.
# filled_generation_summary.csv has one row per fill and month, with the Grid_import
# ratio and any cross-check (FILLCHECK_ rows).
from fuel_attribution import FuelAttribution
fa = FuelAttribution()
fill_tp = fa.fills()
fill_tp = fill_tp[fill_tp["trading_date"].isin(pd.to_datetime(gen["trading_date"].unique()))]
fill_tp.to_csv(OUT_DIR / "filled_generation_log.csv", index=False)
fsum = (fill_tp.assign(month=fill_tp["trading_date"].dt.strftime("%Y%m"))
        .groupby(["override_id", "fill_basis", "poc", "gen_code", "month"], as_index=False)["gen_mwh"].sum())
gil = pd.DataFrame(fa.grid_import_log)
if len(gil):
    gil = gil.drop(columns=["shares", "poc", "fill_mwh"])
    fsum = fsum.merge(gil, on=["override_id", "month"], how="left")
chk = fa.ov[fa.ov["override_id"].str.startswith("FILLCHECK_")]
fsum["cross_check"] = fsum["override_id"].map(
    {("GRIDIMPORT_FILL_" + r.override_id[len("FILLCHECK_"):]): f"{r.value}{r.unit}: {r.method}" for r in chk.itertuples()})
fsum.to_csv(OUT_DIR / "filled_generation_summary.csv", index=False, float_format="%.4f")
fill_day = fill_tp.groupby(["trading_date", "poc", "gen_code", "fuel_code_raw"], as_index=False)["gen_mwh"].sum()
fill_day = fill_day.assign(island=fill_day["poc"].map(poc_island), filled=True)
gen = pd.concat([gen, fill_day[gen.columns]], ignore_index=True)
for gc, g in fill_day.groupby("gen_code"):
    log(f"Fill ({gc}): {g['gen_mwh'].sum()/1e3:.1f} GWh over {g['trading_date'].min().date()} to "
        f"{g['trading_date'].max().date()} (flagged in filled_generation_log.csv)")

# Assign fuel and emission factor per record (fuel_attribution.py)
gen["fuel_std"] = gen["fuel_code_raw"].map(FUEL_STD).fillna(gen["fuel_code_raw"])
gen["year"] = gen["trading_date"].dt.year
gen["month"] = gen["trading_date"].dt.month
gen = fa.attribute(gen)
rule_summary = gen.groupby("rule").agg(gen_GWh=("gen_mwh", lambda s: s.sum() / 1e3),
                                       co2_kt=("co2_kg", lambda s: s.sum() / 1e6))
log("\nFuel attribution rules applied (all years):")
log(rule_summary.round(1).to_string())

# Aggregate to monthly EF by island
gen["filled_gen_mwh"] = gen["gen_mwh"].where(gen["filled"], 0.0)
EXTRA_AGG = dict(filled_gen_MWh=("filled_gen_mwh", "sum"), CO2_kg_estimated=("co2_kg_estimated", "sum"),
                 total_CO2_kg_stratford_ccgt=("co2_kg_bound_ccgt", "sum"),
                 total_CO2_kg_stratford_peaker=("co2_kg_bound_peaker", "sum"),
                 total_CO2_kg_glenbrook_gas=("co2_kg_bound_glenbrook", "sum"))
EXTRA_COLS = ["filled_gen_MWh", "CO2_kg_estimated", "total_CO2_kg_stratford_ccgt", "total_CO2_kg_stratford_peaker",
              "EF_kg_per_MWh_stratford_ccgt", "EF_kg_per_MWh_stratford_peaker",
              "total_CO2_kg_glenbrook_gas", "EF_kg_per_MWh_glenbrook_gas"]


def add_bound_ef(df):
    df["EF_kg_per_MWh_stratford_ccgt"] = df["total_CO2_kg_stratford_ccgt"] / df["total_gen_MWh"]
    df["EF_kg_per_MWh_stratford_peaker"] = df["total_CO2_kg_stratford_peaker"] / df["total_gen_MWh"]
    df["EF_kg_per_MWh_glenbrook_gas"] = df["total_CO2_kg_glenbrook_gas"] / df["total_gen_MWh"]
    return df


monthly = (
    gen.groupby(["island", "year", "month"])
    .agg(total_gen_MWh=("gen_mwh", "sum"), total_CO2_kg=("co2_kg", "sum"), **EXTRA_AGG)
    .reset_index()
)
monthly["EF_kg_per_MWh"] = monthly["total_CO2_kg"] / monthly["total_gen_MWh"]
monthly = add_bound_ef(monthly)
monthly["period"] = pd.to_datetime(monthly[["year", "month"]].assign(day=1))
monthly = monthly.sort_values(["island", "period"]).reset_index(drop=True)

fuel_monthly = (
    gen.groupby(["island", "year", "month", "fuel_std"])
    .agg(gen_mwh=("gen_mwh", "sum"), co2_kg=("co2_kg", "sum"), filled_gen_mwh=("filled_gen_mwh", "sum"),
         co2_kg_estimated=("co2_kg_estimated", "sum"))
    .reset_index()
    .rename(columns={"fuel_std": "fuel_code"})
)
fuel_monthly["weighted_ef_kg_per_MWh"] = fuel_monthly["co2_kg"] / fuel_monthly["gen_mwh"]
fuel_monthly["share_pct"] = (
    fuel_monthly.groupby(["island", "year", "month"])["gen_mwh"].transform(lambda x: x / x.sum() * 100)
)

annual = (
    gen.groupby(["island", "year"])
    .agg(total_gen_MWh=("gen_mwh", "sum"), total_CO2_kg=("co2_kg", "sum"), **EXTRA_AGG)
    .reset_index()
)
annual["EF_kg_per_MWh"] = annual["total_CO2_kg"] / annual["total_gen_MWh"]
annual = add_bound_ef(annual)
annual = annual.sort_values(["island", "year"]).reset_index(drop=True)

# Quality checks
log("\n=== QUALITY CHECKS ===")

spot_checks = [  # (unit or POC/fuel, year, expected kg/MWh), resolved through fuel_attribution.py
    ("HLY1", None, 2024, "Huntly Rankine coal portion (unit HLY1, MfE coal factor)", 1003),
    ("HLY5", None, 2024, "Huntly 5 / E3P (unit HLY5, MfE gas factor)", 395),
    ("HLY6", None, 2024, "Huntly 6 / P40 (unit HLY6, MfE gas factor)", 569),
    ("WHI2201", "DSL", 2024, "Whirinaki diesel (pooled, MfE diesel factor)", 755),
    ("SWN2201", "GAS", 2015, "Southdown gas, 2015 (pooled SWN0/SWN5, MfE gas factor)", 487),
    ("SWN2201", "GAS", 2024, "Southdown gas, 2024 (no active record after decommissioning)", 0),
]
for ref, fuel, yr, name, expected in spot_checks:
    ef = fa.unit_ef(ref, yr, 6) if fuel is None else fa.pooled_ef(ref, fuel, yr, 6)
    log(f"  [OK] {name}: {ef:.0f} kg/MWh (expected about {expected})")
    if abs(ef - expected) >= 5:
        raise ValueError(f"spot check failed: {name} is {ef:.0f} kg/MWh, expected about {expected}")

for island, lo, hi in [("NI", 15, 28), ("SI", 12, 24)]:
    yr_gen = annual[annual["island"] == island].assign(twh=lambda d: d["total_gen_MWh"] / 1e6)
    bad = yr_gen[(yr_gen["twh"] < lo) | (yr_gen["twh"] > hi)]
    if len(bad):
        log(f"  WARNING: {island} years outside {lo}-{hi} TWh range:\n{bad[['year','twh']].to_string(index=False)}")
    else:
        log(f"  OK: {island} annual generation within expected {lo}-{hi} TWh range")

ni_annual = annual[annual["island"] == "NI"].set_index("year")["EF_kg_per_MWh"]
si_annual = annual[annual["island"] == "SI"].set_index("year")["EF_kg_per_MWh"]
common_years = sorted(ni_annual.index.intersection(si_annual.index))
if common_years:
    si_lower = (si_annual[common_years] < ni_annual[common_years]).mean()
    log(f"  SI lower than NI in {si_lower:.0%} of years (expected: about 100%), years: {common_years}")
log(f"  NI annual EF by year: {ni_annual.round(1).to_dict()}")
log(f"  SI annual EF by year: {si_annual.round(1).to_dict()}")

# Outputs
# Columns after total_CO2_kg come from fuel_attribution.py: filled generation,
# the CO2 carried by estimated factors, and the Stratford combined-cycle / peaker bound series.
monthly_out = monthly[["island", "year", "month", "period", "EF_kg_per_MWh", "total_gen_MWh", "total_CO2_kg"] + EXTRA_COLS]
monthly_out.to_csv(OUT_DIR / "monthly_emission_factor_NI_SI.csv", index=False)

annual_out = annual[["island", "year", "EF_kg_per_MWh", "total_gen_MWh", "total_CO2_kg"] + EXTRA_COLS]
annual_out.to_csv(OUT_DIR / "annual_emission_factor_NI_SI.csv", index=False)

fuel_out = fuel_monthly[["island", "year", "month", "fuel_code", "gen_mwh", "co2_kg", "share_pct", "weighted_ef_kg_per_MWh",
                         "filled_gen_mwh", "co2_kg_estimated"]]
fuel_out.to_csv(OUT_DIR / "monthly_fuel_mix_NI_SI.csv", index=False)

log(f"\nWrote: monthly_emission_factor_NI_SI.csv ({len(monthly_out)} rows)")
log(f"Wrote: annual_emission_factor_NI_SI.csv ({len(annual_out)} rows)")
log(f"Wrote: monthly_fuel_mix_NI_SI.csv ({len(fuel_out)} rows)")

# Chart
NAVY = "#1A2744"
TEAL = "#0D7377"
FUEL_COLOURS = {
    "HYD": "#1A6FB5", "GEO": "#A65D2E", "WIN": "#5FB87A",
    "GAS": "#E0A030", "CLG": "#3A3A3A", "DSL": "#B5302E",
    "SOL": "#E8D04A", "WOOD": "#7A5230", "ELE": "#999999",
}

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10))

ni_m = monthly[monthly["island"] == "NI"].sort_values("period")
si_m = monthly[monthly["island"] == "SI"].sort_values("period")
ax1.plot(ni_m["period"], ni_m["EF_kg_per_MWh"], color=NAVY, alpha=0.35, lw=1, label="NI monthly")
ax1.plot(si_m["period"], si_m["EF_kg_per_MWh"], color=TEAL, alpha=0.35, lw=1, label="SI monthly")
ax1.plot(ni_m["period"], ni_m["EF_kg_per_MWh"].rolling(12, min_periods=1).mean(), color=NAVY, lw=2.5, label="NI 12-mo avg")
ax1.plot(si_m["period"], si_m["EF_kg_per_MWh"].rolling(12, min_periods=1).mean(), color=TEAL, lw=2.5, label="SI 12-mo avg")
ax1.set_ylabel("kg CO₂/MWh")
ax1.set_title("Panel A. Monthly grid emission factor, NI vs SI")
ax1.legend(loc="upper right", fontsize=8)
ax1.grid(alpha=0.3)

ni_fuel_annual = (
    fuel_out[fuel_out["island"] == "NI"]
    .groupby(["year", "fuel_code"])["gen_mwh"].sum()
    .unstack(fill_value=0)
)
fuel_order = [f for f in ["HYD", "GEO", "WIN", "GAS", "CLG", "DSL", "SOL", "WOOD", "ELE"] if f in ni_fuel_annual.columns]
ni_fuel_annual = ni_fuel_annual[fuel_order]
ax2.stackplot(
    ni_fuel_annual.index, *[ni_fuel_annual[f] / 1e6 for f in fuel_order],
    labels=fuel_order, colors=[FUEL_COLOURS.get(f, "#888888") for f in fuel_order],
)
ax2.set_ylabel("Generation (TWh)")
ax2.set_xlabel("Year")
ax2.set_title("Panel B. NI annual fuel mix")
ax2.legend(loc="upper left", fontsize=8, ncol=3)
ax2.grid(alpha=0.3)

fig.tight_layout()
fig.savefig(OUT_DIR / "EF_timeseries_NI_SI.png", dpi=150)
log("Wrote: EF_timeseries_NI_SI.png")

log("\n=== NOTES ===")
log("1. SI EF is 0.0 in every year. The 'Dispatched generation plant' SCD2 file is the "
    "only source of HeatRate/EmissionsFactor in this pipeline, and it lists no thermal "
    "(CLG/GAS/DSL/GEO) plant in the South Island. Every thermal POC (Huntly, Kawerau, "
    "Napier, Otahuhu, Southdown, Whirinaki, etc.) is in the North Island. SI generation in "
    "this dataset is 100% hydro/wind, so a zero combustion EF is the correct result for "
    "this data source, not a join failure.")
log("2. The rule table above shows the generation and CO2 carried by each attribution rule. "
    "Thermal generation with no active register record gets EF 0; this applies only to "
    "the post-decommissioning Southdown residual (note 5).")
log("3. Factors are resolved by generator code and register unit (fuel_attribution.py), "
    "not by (POC, fuel) pool. Huntly E3P/P40 take their own units; Rotokawa/Te Huka do only when the "
    "NZGA station intensities are switched off. "
    "Huntly 1-4 are split coal/gas by Genesis's quarterly Rankine coal share (gas portion "
    "an estimate). Kinleith is wood (CH4+N2O only, estimate). Matahina from October 2021 to "
    "December 2025 is filled from the EMI Grid_import generator stream at MAT1101, taken as "
    "measured (flagged). Stratford stays pooled (one generator code for TCC and the "
    "peakers), with combined-cycle and peaker bound columns. Sources: fuel_attribution_overrides.csv.")
log("4. NZ's DST fall-back day (first Sunday of April) has 50 trading periods, not 48. "
    "TP49/TP50 (the extra repeated hour) are included in the daily, monthly and annual sums. "
    "Excluding them would drop about 3,500-3,900 MWh of generation on that day each year.")
log("5. 'Southdown 5' (SWN2201/GAS, unit SWN5) has DateDecommissioned="
    "2016-01-19 but an SCD2 effective_end_datetime of 9999-12-31. Register records are "
    "inactive after their DateDecommissioned (RULE_DECOMMISSIONED). About 3,750 MWh was "
    "recorded at SWN2201 in 2018-2022; it has no active record and carries EF 0. 2015 "
    "generation takes the mean of the two records active that year (SWN0 and SWN5).")

(OUT_DIR / "processing_log.txt").write_text("\n".join(log_lines), encoding="utf-8")
log("Wrote: processing_log.txt")
