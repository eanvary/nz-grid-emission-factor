"""
NI/SI grid emission factor time series at DAILY and HOURLY resolution,
same timeframe (2021-2025) and same methodology as build_ef_timeseries.py
(generation-weighted EF = sum(CO2)/sum(generation), thermal EF from the
Dispatched generation plant SCD2 file evaluated monthly per (POC, fuel)).

This does not touch the monthly/annual pipeline or its outputs.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent  # repo root (this script now lives in generation_pipeline/, one level deeper -- 2026-08 reorg)
NSP_DIR = ROOT / "EA data" / "NSP Tables"
PLANT_FILE = ROOT / "EA data" / "Dispatched generation plant.csv"
GEN_DIR = ROOT / "EA_EMI_raw"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(str(msg))


# ---------------------------------------------------------------------------
# POC -> Island lookup (identical logic to the monthly pipeline)
# ---------------------------------------------------------------------------
nsp_files = sorted(NSP_DIR.glob("*_NetworkSupplyPointsTable.csv"))
nsp_all = pd.concat([pd.read_csv(f, low_memory=False) for f in nsp_files], ignore_index=True)
nsp_unique = nsp_all.drop_duplicates(
    subset=["POC code", "Reconciliation type", "Island", "Start date", "End date"]
)
poc_island = (
    nsp_unique.dropna(subset=["Island"])
    .sort_values("Start date", ascending=False)
    .drop_duplicates(subset=["POC code"])
    .set_index("POC code")["Island"]
    .to_dict()
)
log(f"POC -> Island lookup: {len(poc_island)} POCs")

# ---------------------------------------------------------------------------
# Thermal SCD2 EF lookup, keyed by (POC, standardised fuel)
# ---------------------------------------------------------------------------
plant = pd.read_csv(PLANT_FILE, low_memory=False)
plant["eff_start"] = pd.to_datetime(plant["effective_start_datetime"], utc=True, errors="coerce")
# "9999-12-31..." (still-active record) overflows pandas' nanosecond timestamp
# range and silently parses to NaT with errors="coerce", which would make every
# currently-active SCD2 record fail every date-range match below. Clamp any
# year >= 9999 to an in-range sentinel before parsing (see build_ef_timeseries.py
# for the same fix and rationale).
eff_end_raw = plant["effective_end_datetime"].astype(str).str.replace(
    r"^9999-.*$", "2200-01-01T00:00:00.000Z", regex=True
)
plant["eff_end"] = pd.to_datetime(eff_end_raw, utc=True, errors="coerce")
plant["EF_kg_per_MWh"] = plant["HeatRate"] * plant["EmissionsFactor"] / 1e6

# Item 2 (2026-09-14): real per-station geothermal EF (McLean & Richardson 2019),
# fallback to their fleet mean where unmatched -- see geothermal_ef_correction.py.
from geothermal_ef_correction import apply_geothermal_ef_correction
apply_geothermal_ef_correction(plant)

thermal = plant[plant["EF_kg_per_MWh"].notna()].copy()
thermal_by_pocfuel = {}
for (poc, fuel), g in thermal.groupby(["PointOfConnectionCode", "FuelCode"]):
    thermal_by_pocfuel[(poc, fuel)] = g[["eff_start", "eff_end", "EF_kg_per_MWh"]].to_dict("records")
log(f"Thermal SCD2 lookup built: {len(thermal_by_pocfuel)} (POC, fuel) combinations")

FUEL_STD = {
    "Coal": "CLG", "CLG": "CLG",
    "Gas": "GAS", "GAS": "GAS",
    "Diesel": "DSL", "DSL": "DSL",
    "Geo": "GEO", "GEO": "GEO",
    "Hydro": "HYD", "HYD": "HYD",
    "Solar": "SOL", "SOL": "SOL",
    "Wind": "WIN", "WIN": "WIN",
    "Wood": "WOOD",
    "ELE": "ELE",
}
THERMAL_FUELS = {"CLG", "GAS", "DSL", "GEO"}


def get_thermal_ef(poc, fuel_std, ref_dt):
    records = thermal_by_pocfuel.get((poc, fuel_std))
    if not records:
        return 0.0
    active = [r["EF_kg_per_MWh"] for r in records if r["eff_start"] <= ref_dt < r["eff_end"]]
    if not active:
        return 0.0
    return float(np.mean(active))


# Emission factors are assigned per generator code and unit by fuel_attribution.py (below).
gen_files = sorted(GEN_DIR.glob("*_Generation_MD.csv"))


# ---------------------------------------------------------------------------
# Load each Generation_MD file once, emit both a DAILY row (sum of TP1-48)
# and 24 HOURLY rows (TP[2h+1]+TP[2h+2]) per POC/fuel/date.
# ---------------------------------------------------------------------------
daily_parts = []
hourly_parts = []

for f in gen_files:
    df = pd.read_csv(f, low_memory=False)
    # Column casing changed pre/post ~2020 (Trading_date -> Trading_Date); look
    # up case-insensitively so both eras load identically.
    trading_date_col = {c.lower(): c for c in df.columns}["trading_date"]
    tp_cols = [f"TP{i}" for i in range(1, 49)]
    tp = df[tp_cols].fillna(0).to_numpy(dtype=float)
    # NZ's DST fall-back day (first Sunday of April) has 50 trading periods —
    # TP49/TP50 are the extra repeated hour, present as columns on every file
    # (empty/0 on all other days). Excluded from the 24-hour reshape below (that
    # day's wall-clock hours don't map cleanly to a fixed 24-bucket scheme), but
    # must be added to the DAILY total or that one day, every year, silently loses
    # ~3,500-3,900 MWh nationally.
    tp_extra = df[["TP49", "TP50"]].fillna(0).to_numpy(dtype=float) if "TP49" in df.columns else np.zeros((len(df), 2))

    poc = df["POC_Code"].to_numpy()
    gen_code = df["Gen_Code"].to_numpy()
    fuel_raw = df["Fuel_Code"].to_numpy()
    date = pd.to_datetime(df[trading_date_col]).to_numpy()

    island = pd.Series(poc).map(poc_island).to_numpy()
    fuel_std = pd.Series(fuel_raw).map(FUEL_STD).fillna(pd.Series(fuel_raw)).to_numpy()

    keep = np.array([isl in ("NI", "SI") for isl in island])

    # --- daily (includes TP49/TP50 where present) ---
    daily_mwh = (tp.sum(axis=1) + tp_extra.sum(axis=1)) / 1000.0
    d = pd.DataFrame({
        "island": island[keep], "date": date[keep], "poc": poc[keep], "gen_code": gen_code[keep],
        "fuel_std": fuel_std[keep], "gen_mwh": daily_mwh[keep],
    })
    daily_parts.append(d)

    # --- hourly: pair TP(2h+1)+TP(2h+2) -> hour h (0-23); TP49/TP50 folded into
    # hour 23 (the last hour of the trading day) so the daily hourly-sum still
    # reconciles exactly to the daily total above, without adding a 25th hour
    # bucket that would break every downstream consumer's fixed 24-hour/day shape. ---
    hour_mwh = tp.reshape(len(df), 24, 2).sum(axis=2) / 1000.0  # (n, 24)
    hour_mwh[:, 23] += tp_extra.sum(axis=1) / 1000.0  # kWh -> MWh, matching hour_mwh's units
    n = len(df)
    h_island = np.repeat(island[keep], 24)
    h_poc = np.repeat(poc[keep], 24)
    h_gc = np.repeat(gen_code[keep], 24)
    h_fuel = np.repeat(fuel_std[keep], 24)
    h_date = np.repeat(date[keep], 24)
    h_hour = np.tile(np.arange(24), keep.sum())
    h_mwh = hour_mwh[keep].reshape(-1)
    h = pd.DataFrame({
        "island": h_island, "date": h_date, "hour": h_hour,
        "poc": h_poc, "gen_code": h_gc, "fuel_std": h_fuel, "gen_mwh": h_mwh,
    })
    hourly_parts.append(h)

log(f"Loaded {len(gen_files)} Generation_MD files for daily/hourly disaggregation")

daily_raw = pd.concat(daily_parts, ignore_index=True)
hourly_raw = pd.concat(hourly_parts, ignore_index=True)
daily_raw["filled"] = False
hourly_raw["filled"] = False

# Flagged fills (fuel_attribution.fills: Matahina, Huntly 1-4 September 2020): same trading-period
# values as build_ef_timeseries.py, which writes them to filled_generation_log.csv.
from fuel_attribution import FuelAttribution
fa = FuelAttribution()
fill_tp = fa.fills()
fill_tp = fill_tp[fill_tp["trading_date"].isin(pd.to_datetime(daily_raw["date"].unique()))]
fill_tp["fuel_std"] = fill_tp["fuel_code_raw"].map(FUEL_STD)
fkeys = ["poc", "gen_code", "fuel_std"]
fill_d = fill_tp.groupby(["trading_date"] + fkeys, as_index=False)["gen_mwh"].sum().rename(columns={"trading_date": "date"})
# TP49/TP50 (DST fall-back day) fold into hour 23, as for the raw files above
fill_h = (fill_tp.assign(hour=((fill_tp["tp"] - 1) // 2).clip(upper=23)).groupby(["trading_date", "hour"] + fkeys, as_index=False)["gen_mwh"].sum()
          .rename(columns={"trading_date": "date"}))
for f_ in (fill_d, fill_h):
    f_["island"] = f_["poc"].map(poc_island)
    f_["filled"] = True
daily_raw = pd.concat([daily_raw, fill_d[daily_raw.columns]], ignore_index=True)
hourly_raw = pd.concat([hourly_raw, fill_h[hourly_raw.columns]], ignore_index=True)
log(f"Fills: {fill_d['gen_mwh'].sum()/1e3:.1f} GWh over {fill_d['date'].nunique()} days (flagged)")

frames = {}
for name, d in [("daily", daily_raw), ("hourly", hourly_raw)]:
    d["date"] = pd.to_datetime(d["date"])
    d["year"] = d["date"].dt.year
    d["month"] = d["date"].dt.month
    d = fa.attribute(d)
    d["filled_gen_mwh"] = d["gen_mwh"].where(d["filled"], 0.0)
    frames[name] = d
    log(f"{name}: {len(d):,} generator-level rows, {d['gen_mwh'].sum()/1e6:.2f} TWh total")
daily_raw, hourly_raw = frames["daily"], frames["hourly"]

# ---------------------------------------------------------------------------
# Aggregate to island level. Columns after total_CO2_kg are additions (2026-09-28): filled
# generation, CO2 carried by estimated factors, and the Stratford bound series.
# ---------------------------------------------------------------------------
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


daily_out = (
    daily_raw.groupby(["island", "date"])
    .agg(total_gen_MWh=("gen_mwh", "sum"), total_CO2_kg=("co2_kg", "sum"), **EXTRA_AGG)
    .reset_index()
)
daily_out["EF_kg_per_MWh"] = daily_out["total_CO2_kg"] / daily_out["total_gen_MWh"]
daily_out = add_bound_ef(daily_out)
daily_out = daily_out.sort_values(["island", "date"]).reset_index(drop=True)
daily_out = daily_out[["island", "date", "total_gen_MWh", "total_CO2_kg", "EF_kg_per_MWh"] + EXTRA_COLS]
daily_out.to_csv(OUT_DIR / "daily_emission_factor_NI_SI.csv", index=False)
log(f"Wrote: daily_emission_factor_NI_SI.csv ({len(daily_out)} rows, "
    f"{daily_out['date'].min().date()} to {daily_out['date'].max().date()})")

hourly_out = (
    hourly_raw.groupby(["island", "date", "hour"])
    .agg(total_gen_MWh=("gen_mwh", "sum"), total_CO2_kg=("co2_kg", "sum"), **EXTRA_AGG)
    .reset_index()
)
hourly_out["EF_kg_per_MWh"] = hourly_out["total_CO2_kg"] / hourly_out["total_gen_MWh"]
hourly_out = add_bound_ef(hourly_out)
hourly_out["datetime"] = hourly_out["date"] + pd.to_timedelta(hourly_out["hour"], unit="h")
hourly_out = hourly_out.sort_values(["island", "datetime"]).reset_index(drop=True)
hourly_out = hourly_out[["island", "date", "hour", "datetime", "EF_kg_per_MWh", "total_gen_MWh", "total_CO2_kg"] + EXTRA_COLS]
hourly_out.to_csv(OUT_DIR / "hourly_emission_factor_NI_SI.csv", index=False)
log(f"Wrote: hourly_emission_factor_NI_SI.csv ({len(hourly_out)} rows, "
    f"{hourly_out['datetime'].min()} to {hourly_out['datetime'].max()})")

# ---------------------------------------------------------------------------
# Consistency checks: daily sums must reconcile to monthly; hourly to daily
# ---------------------------------------------------------------------------
log("\n=== CONSISTENCY CHECKS ===")
monthly_existing = pd.read_csv(OUT_DIR / "monthly_emission_factor_NI_SI.csv")

daily_to_monthly = (
    daily_out.assign(year=daily_out["date"].dt.year, month=daily_out["date"].dt.month)
    .groupby(["island", "year", "month"])
    .agg(total_gen_MWh=("total_gen_MWh", "sum"), total_CO2_kg=("total_CO2_kg", "sum"))
    .reset_index()
)
chk = daily_to_monthly.merge(monthly_existing, on=["island", "year", "month"], suffixes=("_daily", "_monthly"))
max_gen_diff = (chk["total_gen_MWh_daily"] - chk["total_gen_MWh_monthly"]).abs().max()
max_co2_diff = (chk["total_CO2_kg_daily"] - chk["total_CO2_kg_monthly"]).abs().max()
log(f"Daily->monthly reconciliation: max |gen diff| = {max_gen_diff:.6f} MWh, "
    f"max |CO2 diff| = {max_co2_diff:.6f} kg (expect ~0)")

hourly_to_daily = (
    hourly_out.groupby(["island", "date"])
    .agg(total_gen_MWh=("total_gen_MWh", "sum"), total_CO2_kg=("total_CO2_kg", "sum"))
    .reset_index()
)
chk2 = hourly_to_daily.merge(daily_out, on=["island", "date"], suffixes=("_hourly", "_daily"))
max_gen_diff2 = (chk2["total_gen_MWh_hourly"] - chk2["total_gen_MWh_daily"]).abs().max()
max_co2_diff2 = (chk2["total_CO2_kg_hourly"] - chk2["total_CO2_kg_daily"]).abs().max()
log(f"Hourly->daily reconciliation: max |gen diff| = {max_gen_diff2:.6f} MWh, "
    f"max |CO2 diff| = {max_co2_diff2:.6f} kg (expect ~0)")

nan_hours = hourly_out["EF_kg_per_MWh"].isna().sum()
log(f"\nNOTE: {nan_hours} hourly rows have EF = NaN (0 generation / 0 CO2). These are "
    f"the DST spring-forward transition hour (last Sunday of September, NZ clocks "
    f"skip 23:00-23:59) where TP47/TP48 do not exist for that POC-day, so total "
    f"generation is genuinely zero for that hour, not a data gap.")
log("\nFuel attribution (2026-09-28): fuel_attribution.py resolves factors by generator code and "
    "register unit, with the sourced overrides in fuel_attribution_overrides.csv (Huntly 1-4 coal/gas "
    "split, E3P/P40 and Rotokawa/Te Huka units, Kinleith wood, Matahina fill, records inactive after "
    "DateDecommissioned). See build_ef_timeseries.py NOTES items 3 and 5.")

(OUT_DIR / "processing_log_daily_hourly.txt").write_text("\n".join(log_lines), encoding="utf-8")
log("Wrote: processing_log_daily_hourly.txt")
