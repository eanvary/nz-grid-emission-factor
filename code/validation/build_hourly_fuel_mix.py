"""
Per-fuel hourly generation table, needed for an hourly (not only monthly) uncertainty band.

The pipeline (generation_pipeline/build_ef_timeseries_daily_hourly.py) computes
a per-POC, per-fuel hourly generation table internally (its own `hourly_raw` DataFrame)
but publishes only the blended total (`hourly_emission_factor_NI_SI.csv`,
island/date/hour/EF/gen/CO2 -- no fuel_std column). This script rebuilds that same
per-fuel hourly table from the same raw inputs, using the IDENTICAL logic (TP-pairing into
24 hours, TP49/TP50 DST handling, flagged fills folded into hours) copied from that script,
and the pipeline's own shared modules for everything else: POC->island map and fuel/factor
attribution from generation_pipeline/fuel_attribution.py (poc_island_map, FuelAttribution:
generator- and unit-level factors, Huntly 1-4 coal/gas split, Kinleith wood, flagged
fills). fuel_std in the output is the attributed fuel, so Huntly 1-4 output appears under
CLG and GAS by the quarterly coal share. The two can disagree only through a bug, not
through a difference in method.

Read-only: touches no pipeline input or output. Writes one new file,
hourly_fuel_mix_NI_SI.csv, into this validation folder (not into output/).

Verification built in: the per-fuel hourly table, summed back to (island, date, hour),
must reproduce the released hourly_emission_factor_NI_SI.csv exactly (energy and EF),
checked below, not assumed.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import FUEL_STD, FuelAttribution, poc_island_map  # noqa: E402

GEN_DIR = ROOT / "EA_EMI_raw"
SHIPPED_HOURLY = ROOT / "output" / "hourly_emission_factor_NI_SI.csv"
OUT = HERE / "hourly_fuel_mix_NI_SI.csv"

print("Loading POC -> Island lookup (fuel_attribution.poc_island_map, as the pipeline)...")
poc_island = poc_island_map()
print(f"  {len(poc_island)} POCs")

fa = FuelAttribution()
gen_files = sorted(GEN_DIR.glob("*_Generation_MD.csv"))

print(f"Loading {len(gen_files)} Generation_MD files and building hourly per-fuel table...")
hourly_parts = []
for f in gen_files:
    df = pd.read_csv(f, low_memory=False)
    trading_date_col = {c.lower(): c for c in df.columns}["trading_date"]
    tp_cols = [f"TP{i}" for i in range(1, 49)]
    tp = df[tp_cols].fillna(0).to_numpy(dtype=float)
    tp_extra = df[["TP49", "TP50"]].fillna(0).to_numpy(dtype=float) if "TP49" in df.columns else np.zeros((len(df), 2))

    poc = df["POC_Code"].to_numpy()
    gen_code = df["Gen_Code"].to_numpy()
    fuel_raw = df["Fuel_Code"].to_numpy()
    date = pd.to_datetime(df[trading_date_col]).to_numpy()
    island = pd.Series(poc).map(poc_island).to_numpy()
    fuel_std = pd.Series(fuel_raw).map(FUEL_STD).fillna(pd.Series(fuel_raw)).to_numpy()
    keep = np.array([isl in ("NI", "SI") for isl in island])

    hour_mwh = tp.reshape(len(df), 24, 2).sum(axis=2) / 1000.0
    hour_mwh[:, 23] += tp_extra.sum(axis=1) / 1000.0
    h_island = np.repeat(island[keep], 24)
    h_poc = np.repeat(poc[keep], 24)
    h_gc = np.repeat(gen_code[keep], 24)
    h_fuel = np.repeat(fuel_std[keep], 24)
    h_date = np.repeat(date[keep], 24)
    h_hour = np.tile(np.arange(24), keep.sum())
    h_mwh = hour_mwh[keep].reshape(-1)
    hourly_parts.append(pd.DataFrame({
        "island": h_island, "date": h_date, "hour": h_hour,
        "poc": h_poc, "gen_code": h_gc, "fuel_std": h_fuel, "gen_mwh": h_mwh,
    }))

hourly_raw = pd.concat(hourly_parts, ignore_index=True)
hourly_raw["date"] = pd.to_datetime(hourly_raw["date"])

# Flagged fills (fuel_attribution.fills), folded into hours as build_ef_timeseries_daily_hourly.py
# does: TP49/TP50 go to hour 23.
fill_tp = fa.fills()
fill_tp = fill_tp[fill_tp["trading_date"].isin(hourly_raw["date"].unique())]
fill_tp["fuel_std"] = fill_tp["fuel_code_raw"].map(FUEL_STD)
fill_h = (fill_tp.assign(hour=((fill_tp["tp"] - 1) // 2).clip(upper=23))
          .groupby(["trading_date", "hour", "poc", "gen_code", "fuel_std"], as_index=False)["gen_mwh"].sum()
          .rename(columns={"trading_date": "date"}))
fill_h["island"] = fill_h["poc"].map(poc_island)
hourly_raw = pd.concat([hourly_raw, fill_h[hourly_raw.columns]], ignore_index=True)
print(f"  fills: {fill_h['gen_mwh'].sum()/1e3:.1f} GWh (flagged)")

hourly_raw["year"] = hourly_raw["date"].dt.year
hourly_raw["month"] = hourly_raw["date"].dt.month
hourly_raw = fa.attribute(hourly_raw)  # fuel_std becomes the attributed fuel; co2_kg added
print(f"  {len(hourly_raw):,} POC-level hourly rows, {hourly_raw['gen_mwh'].sum()/1e6:.2f} TWh total")

# Aggregate to (island, date, hour, fuel_std): the finer product this script adds.
fuel_hourly = (
    hourly_raw.groupby(["island", "date", "hour", "fuel_std"])
    .agg(gen_mwh=("gen_mwh", "sum"), co2_kg=("co2_kg", "sum"))
    .reset_index()
)
fuel_hourly["ef_kg_per_mwh"] = np.where(
    fuel_hourly["gen_mwh"] > 0, fuel_hourly["co2_kg"] / fuel_hourly["gen_mwh"], 0.0
)
fuel_hourly.to_csv(OUT, index=False)
print(f"Wrote {len(fuel_hourly):,} rows -> {OUT}")

# Verification: sum this new per-fuel table back to (island, date, hour) and
# compare against the released hourly_emission_factor_NI_SI.csv.
print("\nVerifying against shipped hourly_emission_factor_NI_SI.csv...")
recombined = (
    fuel_hourly.groupby(["island", "date", "hour"])
    .agg(total_gen_MWh=("gen_mwh", "sum"), total_CO2_kg=("co2_kg", "sum"))
    .reset_index()
)
recombined["EF_kg_per_MWh"] = recombined["total_CO2_kg"] / recombined["total_gen_MWh"]

shipped = pd.read_csv(SHIPPED_HOURLY)
shipped["date"] = pd.to_datetime(shipped["date"])
merged = recombined.merge(shipped, on=["island", "date", "hour"], suffixes=("_new", "_shipped"))
assert len(merged) == len(shipped) == len(recombined), (
    f"row count mismatch: new={len(recombined)} shipped={len(shipped)} merged={len(merged)}"
)
gen_diff = (merged["total_gen_MWh_new"] - merged["total_gen_MWh_shipped"]).abs()
ef_diff = (merged["EF_kg_per_MWh_new"] - merged["EF_kg_per_MWh_shipped"]).abs()
print(f"  rows compared: {len(merged):,}")
print(f"  max |gen diff|: {gen_diff.max():.6f} MWh   (mean {gen_diff.mean():.8f})")
print(f"  max |EF diff|:  {ef_diff.max():.6f} kg/MWh (mean {ef_diff.mean():.8f})")
assert gen_diff.max() < 1e-6, "generation reconciliation FAILED"
assert ef_diff.max() < 1e-6, "EF reconciliation FAILED"
print("  PASS -- per-fuel hourly table reconciles exactly to the shipped hourly output.")
