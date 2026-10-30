"""
NI/SI grid emission factor time series at daily and hourly resolution.
Period and method match build_ef_timeseries.py: every Generation_MD month on
up to LAST_MONTH (2015-2025), generation-weighted
EF = sum(CO2)/sum(generation), with factors resolved per month by
fuel_attribution.py from the Dispatched generation plant register.

The monthly and annual outputs are not modified.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent  # project root: the folder above generation_pipeline/
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(str(msg))


from fuel_attribution import FUEL_STD, periods_in_day, poc_island_map, raw_files, tp_hours, tp_to_hours

poc_island = poc_island_map()
log(f"POC-to-island lookup: {len(poc_island)} POCs")

# Emission factors are assigned per generator code and unit by fuel_attribution.py (below).
gen_files = raw_files("Generation_MD")


# Each Generation_MD file is loaded once and gives a daily row (all trading periods)
# and one row per local clock hour per POC/fuel/date.
daily_parts = []
hourly_parts = []

for f in gen_files:
    df = pd.read_csv(f, low_memory=False)
    # The column is Trading_date in older files and Trading_Date in later ones
    # (the change is around 2020); a case-insensitive lookup loads both.
    trading_date_col = {c.lower(): c for c in df.columns}["trading_date"]
    # TP1-TP50: 46 periods when clocks go forward, 50 when they go back (TP49/TP50 present).
    tp = df.reindex(columns=[f"TP{i}" for i in range(1, 51)]).fillna(0).to_numpy(dtype=float)

    poc = df["POC_Code"].to_numpy()
    gen_code = df["Gen_Code"].to_numpy()
    fuel_raw = df["Fuel_Code"].to_numpy()
    date = pd.to_datetime(df[trading_date_col]).to_numpy()

    island = pd.Series(poc).map(poc_island).to_numpy()
    fuel_std = pd.Series(fuel_raw).map(FUEL_STD).fillna(pd.Series(fuel_raw)).to_numpy()

    keep = np.array([isl in ("NI", "SI") for isl in island])

    daily_mwh = tp.sum(axis=1) / 1000.0
    d = pd.DataFrame({
        "island": island[keep], "date": date[keep], "poc": poc[keep], "gen_code": gen_code[keep],
        "fuel_std": fuel_std[keep], "gen_mwh": daily_mwh[keep],
    })
    daily_parts.append(d)

    # Hourly by local clock hour. On the clocks-forward day 02:00 does not exist (NaN, dropped
    # below); on the clocks-back day both runs of 02:00 sum into hour 2.
    hour_mwh = tp_to_hours(tp, periods_in_day(date)) / 1000.0  # (n, 24), kWh to MWh
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
    hourly_parts.append(h.dropna(subset=["gen_mwh"]))

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
hour_of = {n: tp_hours(n) for n in (46, 48, 50)}
fill_tp["hour"] = [hour_of[n][t - 1] for n, t in zip(periods_in_day(fill_tp["trading_date"]), fill_tp["tp"])]
fill_h = (fill_tp.groupby(["trading_date", "hour"] + fkeys, as_index=False)["gen_mwh"].sum()
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

# Aggregate to island level. Columns after total_CO2_kg: filled
# generation, CO2 carried by estimated factors, and the Stratford bound series.
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

# Consistency checks: daily sums must reconcile to monthly; hourly to daily
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
log(f"Daily-to-monthly reconciliation: max |gen diff| = {max_gen_diff:.6f} MWh, "
    f"max |CO2 diff| = {max_co2_diff:.6f} kg (expected: about 0)")
assert len(chk) == len(monthly_existing), "daily output is missing months that the monthly output has"
for c in ("total_gen_MWh", "total_CO2_kg"):
    assert np.allclose(chk[f"{c}_daily"], chk[f"{c}_monthly"], rtol=1e-9), f"daily {c} does not sum to monthly"

hourly_to_daily = (
    hourly_out.groupby(["island", "date"])
    .agg(total_gen_MWh=("total_gen_MWh", "sum"), total_CO2_kg=("total_CO2_kg", "sum"))
    .reset_index()
)
chk2 = hourly_to_daily.merge(daily_out, on=["island", "date"], suffixes=("_hourly", "_daily"))
max_gen_diff2 = (chk2["total_gen_MWh_hourly"] - chk2["total_gen_MWh_daily"]).abs().max()
max_co2_diff2 = (chk2["total_CO2_kg_hourly"] - chk2["total_CO2_kg_daily"]).abs().max()
log(f"Hourly-to-daily reconciliation: max |gen diff| = {max_gen_diff2:.6f} MWh, "
    f"max |CO2 diff| = {max_co2_diff2:.6f} kg (expected: about 0)")
assert len(chk2) == len(daily_out), "hourly output is missing days that the daily output has"
for c in ("total_gen_MWh", "total_CO2_kg"):
    assert np.allclose(chk2[f"{c}_hourly"], chk2[f"{c}_daily"], rtol=1e-9), f"hourly {c} does not sum to daily"

nan_hours = int(hourly_out["EF_kg_per_MWh"].isna().sum())
log(f"\nNOTE: hours are local clock hours. The clocks-forward day (last Sunday of September) has no "
    f"02:00 row; on the clocks-back day (first Sunday of April) hour 2 holds both runs of 02:00. "
    f"Hourly rows with EF = NaN: {nan_hours} (expected 0).")
assert nan_hours == 0, "hourly rows with no emission factor"
log("\nFuel attribution: fuel_attribution.py resolves factors by generator code and "
    "register unit, with the sourced overrides in fuel_attribution_overrides.csv (Huntly 1-4 coal/gas "
    "split, E3P/P40 units, Kinleith wood, Matahina fill, records inactive after "
    "DateDecommissioned). See build_ef_timeseries.py NOTES items 3 and 5.")

(OUT_DIR / "processing_log_daily_hourly.txt").write_text("\n".join(log_lines), encoding="utf-8")
log("Wrote: processing_log_daily_hourly.txt")
