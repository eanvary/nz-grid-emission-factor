"""
Module 4 (Assumption 1): build normalised hourly shape templates, by
island, from the historical EA/EMI data. These are the only non-MBIE,
non-battery inputs the pipeline uses, and they are Assumption 1.

Produces, for four template years chosen by national hydro (central / median / wet / dry):
  - per (island, renewable fuel) normalised hourly profile  [weight sums to 1/yr]
  - per island normalised hourly demand profile             [weight sums to 1/yr]

Template years (ranked on national hydro TWh from monthly_fuel_mix_NI_SI.csv):
  central = 2021 (23.34 TWh) ; median = 2017 (24.22, true
  median of the full 11-year 2015-2025 record) ; wet = 2023 (25.37) ; dry = 2024 (22.73)
The wet/dry pair is the Assumption-1 sensitivity case.

"central" (2021) is the reference template.
"median" (2017) is a 4th, representative template, ranked against the full 11-year
2015-2025 record. 2021 was chosen on the 2021-2025 window only and is the 3rd-driest of 11
years (18th percentile), not the median. 2023/2024 are the wettest/driest of all 11 years,
not just of 2021-2025. Selecting a template changes only the hourly timing shape; annual
volume is always MBIE's template-invariant figure, so adding "median" changes no result
built on "central".

Renewable profiles are rebuilt per-fuel from raw Generation_MD (the existing
hourly output collapses fuel); demand profiles come from the Consumption
pipeline's hourly island output. Both reuse the historical POC-to-island lookup.

source_tag = assumption_1

Outputs (output/edgs/):
  edgs_shape_renewables.parquet  template_year, island, fuel_std, month, day, hour, weight
  edgs_shape_demand.parquet      template_year, island, month, day, hour, weight
"""
import sys

import numpy as np
import pandas as pd

from edgs_common import ROOT, OUT_DIR, CONSUMPTION_OUT, log_factory

sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import periods_in_day, tp_to_hours  # noqa: E402

log, lines = log_factory()

TEMPLATE_YEARS = {"central": 2021, "median": 2017, "wet": 2023, "dry": 2024}
RENEWABLE_FUELS = ["HYD", "WIN", "SOL", "GEO", "WOOD"]
NSP_DIR = ROOT / "EA data" / "NSP Tables"
GEN_DIR = ROOT / "EA_EMI_raw"

FUEL_STD = {  # identical mapping to build_ef_timeseries.py
    "Coal": "CLG", "CLG": "CLG", "Gas": "GAS", "GAS": "GAS",
    "Diesel": "DSL", "DSL": "DSL", "Geo": "GEO", "GEO": "GEO",
    "Hydro": "HYD", "HYD": "HYD", "Solar": "SOL", "SOL": "SOL",
    "Wind": "WIN", "WIN": "WIN", "Wood": "WOOD", "ELE": "ELE",
}

# POC to island (same logic as the historical pipeline)
nsp = pd.concat([pd.read_csv(f, low_memory=False) for f in NSP_DIR.glob("*_NetworkSupplyPointsTable.csv")],
                ignore_index=True)
poc_island = (nsp.dropna(subset=["Island"])
              .sort_values("Start date", ascending=False)
              .drop_duplicates(subset=["POC code"])
              .set_index("POC code")["Island"].to_dict())
log(f"POC-to-island lookup: {len(poc_island)} POCs")

# Renewable per-fuel per-island hourly, template years only
want_years = set(TEMPLATE_YEARS.values())
gen_files = [f for f in sorted(GEN_DIR.glob("*_Generation_MD.csv")) if int(f.name[:4]) in want_years]
log(f"Loading {len(gen_files)} Generation_MD files for template years {sorted(want_years)}")

parts = []
for f in gen_files:
    df = pd.read_csv(f, low_memory=False)
    # Column casing differs before 2020 (Trading_date or Trading_Date), which matters
    # for the "median" (2017) template; same case-insensitive lookup as
    # build_ef_timeseries.py's lower_map.
    lower_map = {c.lower(): c for c in df.columns}
    tp = df.reindex(columns=[f"TP{i}" for i in range(1, 51)]).fillna(0).to_numpy(float)
    n_tp = periods_in_day(df[lower_map["trading_date"]])
    hour_mwh = tp_to_hours(tp, n_tp) / 1000.0  # (n, 24) local clock hours, MWh
    # A shape needs one value per clock hour: the clocks-back day's repeated 02:00 is averaged,
    # and the clocks-forward day's missing 02:00 is taken as the mean of 01:00 and 03:00.
    hour_mwh[n_tp == 50, 2] /= 2
    fwd = n_tp == 46
    hour_mwh[fwd, 2] = (hour_mwh[fwd, 1] + hour_mwh[fwd, 3]) / 2
    island = pd.Series(df[lower_map["poc_code"]]).map(poc_island).to_numpy()
    fuel = pd.Series(df[lower_map["fuel_code"]]).map(FUEL_STD).fillna(df[lower_map["fuel_code"]]).to_numpy()
    date = pd.to_datetime(df[lower_map["trading_date"]])
    keep = np.array([i in ("NI", "SI") for i in island])
    n = keep.sum()
    parts.append(pd.DataFrame({
        "island": np.repeat(island[keep], 24),
        "fuel_std": np.repeat(fuel[keep], 24),
        "year": np.repeat(date.dt.year.to_numpy()[keep], 24),
        "month": np.repeat(date.dt.month.to_numpy()[keep], 24),
        "day": np.repeat(date.dt.day.to_numpy()[keep], 24),
        "hour": np.tile(np.arange(24), n),
        "mwh": hour_mwh[keep].reshape(-1),
    }))

raw = pd.concat(parts, ignore_index=True)
ren = raw[raw["fuel_std"].isin(RENEWABLE_FUELS)]
ren = (ren.groupby(["year", "island", "fuel_std", "month", "day", "hour"], as_index=False)["mwh"].sum())

# normalise to weight (sum=1) per (year, island, fuel)
ren["weight"] = ren["mwh"] / ren.groupby(["year", "island", "fuel_std"])["mwh"].transform("sum")
ren["template_year"] = ren["year"]
ren_out = ren[["template_year", "island", "fuel_std", "month", "day", "hour", "weight"]].copy()

# report normalisation + coverage
chk = ren.groupby(["year", "island", "fuel_std"])["weight"].sum()
log(f"Renewable profiles: {len(ren_out):,} rows; weight-sum range {chk.min():.4f}-{chk.max():.4f} (expect 1.0)")
for isl in ("NI", "SI"):
    fuels = sorted(ren_out[ren_out.island == isl]["fuel_std"].unique())
    log(f"  {isl} renewable fuels with a profile: {fuels}")

# Demand per-island hourly (Consumption pipeline output)
cons = pd.read_csv(CONSUMPTION_OUT / "hourly_consumption_EF_NI_SI.csv")
cons["datetime"] = pd.to_datetime(cons["datetime"])
cons = cons[cons["datetime"].dt.year.isin(want_years)]
dem_long = []
for isl, col in [("NI", "NI_consumption_MWh"), ("SI", "SI_consumption_MWh")]:
    d = pd.DataFrame({
        "template_year": cons["datetime"].dt.year, "island": isl,
        "month": cons["datetime"].dt.month, "day": cons["datetime"].dt.day,
        "hour": cons["datetime"].dt.hour, "mwh": cons[col].to_numpy(),
    })
    dem_long.append(d)
dem = pd.concat(dem_long, ignore_index=True)
# Same one-value-per-clock-hour rule as the renewable shapes above.
dem = dem.pivot_table(index=["template_year", "island", "month", "day"], columns="hour", values="mwh", aggfunc="sum")
n_tp = periods_in_day(pd.to_datetime(dem.index.to_frame(index=False)[["template_year", "month", "day"]]
                                     .rename(columns={"template_year": "year"})))
dem.loc[n_tp == 50, 2] /= 2
dem.loc[n_tp == 46, 2] = (dem.loc[n_tp == 46, 1] + dem.loc[n_tp == 46, 3]) / 2
dem = dem.stack().rename("mwh").reset_index()
dem["weight"] = dem["mwh"] / dem.groupby(["template_year", "island"])["mwh"].transform("sum")
dem_out = dem[["template_year", "island", "month", "day", "hour", "weight"]].copy()
dchk = dem.groupby(["template_year", "island"])["weight"].sum()
log(f"\nDemand profiles: {len(dem_out):,} rows; weight-sum range {dchk.min():.4f}-{dchk.max():.4f} (expect 1.0)")

# peak-hour fraction sanity check (a single hour's share of the annual total, x8760, gives the peak/avg ratio)
for ty in sorted(want_years):
    for isl in ("NI", "SI"):
        w = dem_out[(dem_out.template_year == ty) & (dem_out.island == isl)]["weight"]
        if len(w):
            log(f"  {ty} {isl}: peak/avg demand ratio about {w.max()*len(w):.2f}")

ren_out.to_parquet(OUT_DIR / "edgs_shape_renewables.parquet", index=False)
dem_out.to_parquet(OUT_DIR / "edgs_shape_demand.parquet", index=False)
log(f"\nTemplate years: {TEMPLATE_YEARS}")
log("Wrote edgs_shape_renewables.parquet and edgs_shape_demand.parquet")
(OUT_DIR / "processing_log_hourly_shape.txt").write_text("\n".join(lines), encoding="utf-8")
