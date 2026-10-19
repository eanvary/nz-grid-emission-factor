"""
Module 4 — Step 4 (Assumption 1): build normalised hourly SHAPE templates, by
island, from the user's historical EA/EMI data. These are the only non-MBIE,
non-battery inputs the pipeline uses, and they are Assumption 1.

Produces, for four template years chosen by national hydro (central / median / wet / dry):
  - per (island, renewable fuel) normalised hourly profile  [weight sums to 1/yr]
  - per island normalised hourly DEMAND profile             [weight sums to 1/yr]

Template years (ranked on national hydro TWh from monthly_fuel_mix_NI_SI.csv):
  central = 2021 (23.34 TWh, originally labelled "median") ; median = 2017 (24.22, true
  median of the full 11-year 2015-2025 record) ; wet = 2023 (25.37) ; dry = 2024 (22.73)
The wet/dry pair is the Assumption-1 sensitivity case (brief Section 4).

APPLIED (2026-08-11, Design B of PLAN_11YEAR_TEMPLATE_REASSESSMENT.md): "central" (2021) is
KEPT, not replaced -- every figure in Briefs B-H of README_EDGS_hourly.md is anchored to it
and this change is deliberately additive, not destructive. "median" (2017) is ADDED as a 4th,
genuinely-representative template, re-ranked against the full 11-year 2015-2025 record (2021
was only ever checked against the 2021-2025 window that existed when it was first chosen, and
turns out to be the 3rd-driest of 11 years / 18th percentile, not the median). 2023/2024 are
unaffected by the extension (still correctly the wettest/driest of all 11 years, not just the
original 5). Adding "median" does not change any previously-shipped number (only the hourly
TIMING shape depends on which template is selected; annual volume is always MBIE's own
template-invariant figure). See EDGS_Pipeline_Complete_Documentation.md Section 8.5 and
README_EDGS_hourly.md Brief K for the original analysis and now Brief M for what changed.

Renewable profiles are rebuilt per-fuel from raw Generation_MD (the existing
hourly output collapses fuel); demand profiles come from the Consumption
pipeline's hourly island output. Both reuse the historical POC->Island lookup.

source_tag = assumption_1

Outputs (output/edgs/):
  edgs_shape_renewables.parquet  template_year, island, fuel_std, month, day, hour, weight
  edgs_shape_demand.parquet      template_year, island, month, day, hour, weight
"""
import numpy as np
import pandas as pd

from edgs_common import ROOT, OUT_DIR, HIST_OUT, CONSUMPTION_OUT, log_factory

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

# ---------------------------------------------------------------------------
# POC -> Island (same logic as the historical pipeline)
# ---------------------------------------------------------------------------
nsp = pd.concat([pd.read_csv(f, low_memory=False) for f in NSP_DIR.glob("*_NetworkSupplyPointsTable.csv")],
                ignore_index=True)
poc_island = (nsp.dropna(subset=["Island"])
              .sort_values("Start date", ascending=False)
              .drop_duplicates(subset=["POC code"])
              .set_index("POC code")["Island"].to_dict())
log(f"POC->Island lookup: {len(poc_island)} POCs")

# ---------------------------------------------------------------------------
# Renewable per-fuel per-island hourly, template years only
# ---------------------------------------------------------------------------
want_years = set(TEMPLATE_YEARS.values())
gen_files = [f for f in sorted(GEN_DIR.glob("*_Generation_MD.csv")) if int(f.name[:4]) in want_years]
log(f"Loading {len(gen_files)} Generation_MD files for template years {sorted(want_years)}")

parts = []
for f in gen_files:
    df = pd.read_csv(f, low_memory=False)
    tp = df[[f"TP{i}" for i in range(1, 49)]].fillna(0).to_numpy(float)
    hour_mwh = tp.reshape(len(df), 24, 2).sum(axis=2) / 1000.0  # (n,24) pair TPs -> hours
    # FIX (2026-08-10, found by the systematic reliability assessment, NOT YET picked
    # up by the currently-shipped edgs_shape_*.parquet -- see
    # DATA_QUALITY_ASSESSMENT_FRAMEWORK.md): NZ's DST fall-back day (first Sunday of
    # April) has 50 trading periods; TP49/TP50 were previously dropped entirely,
    # missing ~3,500-3,900 MWh nationally on that one day in each of 2021/2023/2024.
    # Folded into hour 23 for the same reason as build_ef_timeseries_daily_hourly.py
    # (avoids adding a 25th hour bucket that would break the fixed 24-hour/day shape
    # every downstream consumer of edgs_shape_*.parquet assumes). Negligible in
    # magnitude (<0.02% of one fuel's one year's total) -- not, by itself, sufficient
    # reason to trigger a full re-run of the shipped forward pipeline (Modules 5-7 and
    # every downstream Brief); left as a documented, ready-to-pick-up fix for whoever
    # next regenerates the shipped output for any other reason.
    if "TP49" in df.columns:
        tp_extra = df[["TP49", "TP50"]].fillna(0).to_numpy(float)
        hour_mwh[:, 23] += tp_extra.sum(axis=1) / 1000.0
    # Column casing changed pre-2020 (Trading_date -> Trading_Date); the 2015-2025
    # extension exposed this for the new "median" (2017) template -- same fix as
    # build_ef_timeseries.py's lower_map, applied here too (2026-08-11).
    lower_map = {c.lower(): c for c in df.columns}
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

# ---------------------------------------------------------------------------
# Demand per-island hourly (Consumption pipeline output)
# ---------------------------------------------------------------------------
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
dem["weight"] = dem["mwh"] / dem.groupby(["template_year", "island"])["mwh"].transform("sum")
dem_out = dem[["template_year", "island", "month", "day", "hour", "weight"]].copy()
dchk = dem.groupby(["template_year", "island"])["weight"].sum()
log(f"\nDemand profiles: {len(dem_out):,} rows; weight-sum range {dchk.min():.4f}-{dchk.max():.4f} (expect 1.0)")

# peak-hour fraction sanity (a single hour's share of annual, x8760 -> peak/avg ratio)
for ty in sorted(want_years):
    for isl in ("NI", "SI"):
        w = dem_out[(dem_out.template_year == ty) & (dem_out.island == isl)]["weight"]
        if len(w):
            log(f"  {ty} {isl}: peak/avg demand ratio ~ {w.max()*len(w):.2f}")

ren_out.to_parquet(OUT_DIR / "edgs_shape_renewables.parquet", index=False)
dem_out.to_parquet(OUT_DIR / "edgs_shape_demand.parquet", index=False)
log(f"\nTemplate years: {TEMPLATE_YEARS}")
log("Wrote edgs_shape_renewables.parquet + edgs_shape_demand.parquet")
(OUT_DIR / "processing_log_hourly_shape.txt").write_text("\n".join(lines), encoding="utf-8")
