"""
Inter-island (HVDC, Cook Strait link) power transfer, 2015-2025, from the raw
EMI "HVDC flows" metered dataset (../EA_EMI_raw/*_HVDC_flows.csv, the root
pipeline's shared raw-data folder; this script keeps no copy of its own).
The hand-exported EMI report file is not used, since it covers only 2021-2025.

The HVDC transfer outputs live in this folder, since both the consumption-EF
calculation (this folder) and the generation-side pipeline (root) need them.
Raw inputs are read from the root-level shared EA_EMI_raw/ folder (single
source of truth, no duplicate local copy that could go stale); only the
output is written here.

Convention: energy transfer is read at the receiving end's Import (I) flow
direction at each converter station. This is the delivered-energy reading,
already net of DC-link losses:
  - Northward (SI to NI) = HAY2201 (Haywards, NI) Flow_Direction "I"
  - Southward (NI to SI) = BEN2201 (Benmore, SI) Flow_Direction "I"
"""
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
ROOT_ROOT = ROOT.parent  # repo root, one level up
ROOT_OUT = ROOT_ROOT / "output"       # root pipeline's generation-EF output (read-only from here)
OUT_DIR = ROOT / "output"             # this folder's own output (HVDC transfer tables)
OUT_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT_ROOT / "generation_pipeline"))
from fuel_attribution import periods_in_day, raw_files, tp_to_hours  # noqa: E402

NAVY = "#1A2744"
TEAL = "#0D7377"
GOLD = "#C9A227"

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(str(msg))


# Load all raw HVDC_flows files, normalising pre/post-2020 column casing
files = raw_files("HVDC_flows")
log(f"Found {len(files)} raw HVDC_flows files")

parts = []
hourly_parts = []
for f in files:
    df = pd.read_csv(f, low_memory=False)
    lower_map = {c.lower(): c for c in df.columns}
    poc_col = lower_map["poc"]
    dir_col = lower_map["flow_direction"]
    date_col = lower_map["trading_date"]
    # <=50, not <=48: NZ's DST fall-back day (first Sunday of April) has 50
    # trading periods; TP49/TP50 must be included or that day's flow is undercounted.
    tp_cols = [c for c in df.columns if re.match(r"^TP\d+$", c) and int(c[2:]) <= 50]

    keep = df[poc_col].isin(["BEN2201", "HAY2201"]) & (df[dir_col] == "I")
    d = df.loc[keep, [poc_col, date_col] + tp_cols].copy()
    d = d.rename(columns={poc_col: "poc", date_col: "trading_date"})
    # Raw files switch date format partway through the series. Pre-2020 files
    # are DD/MM/YYYY ("01/04/2015"); 2020-onward files are ISO YYYY-MM-DD
    # ("2020-04-01"). A single pd.to_datetime(..., format="mixed", dayfirst=True)
    # call is unsafe for the ISO files. In "mixed" mode pandas' dayfirst flag still
    # swaps day and month whenever both are <=12, though ISO YYYY-MM-DD is
    # unambiguous, so "2020-04-01" (April 1) parses as 2020-01-04 (Jan 4). That
    # would corrupt the 1st-12th of every month in every 2020+ file, scattering
    # data across up to 12 wrong months of the same year. Annual totals survive,
    # because the swap never crosses a year boundary; daily, hourly and monthly
    # figures do not. Each era is therefore parsed with its own explicit format.
    parsed_iso = pd.to_datetime(d["trading_date"], format="%Y-%m-%d", errors="coerce")
    parsed_slash = pd.to_datetime(d["trading_date"], format="%d/%m/%Y", errors="coerce")
    d["trading_date"] = parsed_iso.fillna(parsed_slash)
    if d["trading_date"].isna().any():
        bad = df.loc[keep, date_col][d["trading_date"].isna()].unique()
        raise ValueError(f"{f.name}: {len(bad)} trading_date value(s) matched neither "
                          f"YYYY-MM-DD nor DD/MM/YYYY: {bad[:10]}")
    d["gwh"] = d[tp_cols].fillna(0).sum(axis=1) / 1e6  # kWh to GWh
    parts.append(d[["poc", "trading_date", "gwh"]])

    # Hourly by local clock hour, as in the generation-side hourly pipeline (fuel_attribution.tp_to_hours).
    tp50 = df.loc[keep].reindex(columns=[f"TP{i}" for i in range(1, 51)]).fillna(0).to_numpy(dtype=float)
    hour_mwh = tp_to_hours(tp50, periods_in_day(d["trading_date"])) / 1000.0  # kWh to MWh, shape (n, 24)
    n = len(d)
    hourly_parts.append(pd.DataFrame({
        "poc": np.repeat(d["poc"].to_numpy(), 24),
        "trading_date": np.repeat(d["trading_date"].to_numpy(), 24),
        "hour": np.tile(np.arange(24), n),
        "mwh": hour_mwh.reshape(-1),
    }).dropna(subset=["mwh"]))

raw = pd.concat(parts, ignore_index=True)
log(f"Loaded {len(raw):,} POC-day import records, "
    f"{raw['trading_date'].min().date()} to {raw['trading_date'].max().date()}")

wide = raw.pivot_table(index="trading_date", columns="poc", values="gwh", aggfunc="sum").fillna(0.0)
wide = wide.rename(columns={"HAY2201": "SI_to_NI_GWh", "BEN2201": "NI_to_SI_GWh"})
wide["net_to_NI_GWh"] = wide["SI_to_NI_GWh"] - wide["NI_to_SI_GWh"]
wide = wide.reset_index().rename(columns={"trading_date": "date"})
wide["year"] = wide["date"].dt.year
wide["month"] = wide["date"].dt.month

# Aggregate and write outputs (daily, monthly, annual, hourly), full 2015-2025
daily = wide[["date", "SI_to_NI_GWh", "NI_to_SI_GWh", "net_to_NI_GWh"]].sort_values("date")
daily.to_csv(OUT_DIR / "daily_hvdc_transfer_NI_SI.csv", index=False)
log(f"\nWrote daily_hvdc_transfer_NI_SI.csv ({len(daily)} rows, "
    f"{daily['date'].min().date()} to {daily['date'].max().date()})")

hourly_raw = pd.concat(hourly_parts, ignore_index=True)
hourly_wide = hourly_raw.pivot_table(index=["trading_date", "hour"], columns="poc", values="mwh", aggfunc="sum").fillna(0.0)
hourly_wide = hourly_wide.rename(columns={"HAY2201": "SI_to_NI_MWh", "BEN2201": "NI_to_SI_MWh"})
hourly_wide["net_to_NI_MWh"] = hourly_wide["SI_to_NI_MWh"] - hourly_wide["NI_to_SI_MWh"]
hourly_wide = hourly_wide.reset_index().rename(columns={"trading_date": "date"})
hourly_wide["datetime"] = hourly_wide["date"] + pd.to_timedelta(hourly_wide["hour"], unit="h")
hourly_wide = hourly_wide.sort_values("datetime").reset_index(drop=True)
hourly_out_cols = ["date", "hour", "datetime", "SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh"]
hourly_wide[hourly_out_cols].to_csv(OUT_DIR / "hourly_hvdc_transfer_NI_SI.csv", index=False)
log(f"Wrote hourly_hvdc_transfer_NI_SI.csv ({len(hourly_wide)} rows)")

h2d = hourly_wide.groupby("date").agg(
    SI_to_NI_GWh=("SI_to_NI_MWh", lambda s: s.sum() / 1000),
    NI_to_SI_GWh=("NI_to_SI_MWh", lambda s: s.sum() / 1000),
).reset_index()
chk_h2d = h2d.merge(daily, on="date", suffixes=("_h", "_d"))
max_h2d_diff = (chk_h2d["SI_to_NI_GWh_h"] - chk_h2d["SI_to_NI_GWh_d"]).abs().max()
log(f"Hourly-to-daily reconciliation: max |SI_to_NI diff| = {max_h2d_diff:.9f} GWh (expected: about 0)")
assert len(chk_h2d) == len(daily), "hourly HVDC output is missing days that the daily output has"
for c in ("SI_to_NI_GWh", "NI_to_SI_GWh"):
    assert np.allclose(chk_h2d[f"{c}_h"], chk_h2d[f"{c}_d"], rtol=1e-9), f"hourly {c} does not sum to daily"

monthly = (
    wide.groupby(["year", "month"])[["SI_to_NI_GWh", "NI_to_SI_GWh", "net_to_NI_GWh"]]
    .sum()
    .reset_index()
)
monthly["period"] = pd.to_datetime(monthly[["year", "month"]].assign(day=1))
monthly = monthly.sort_values("period").reset_index(drop=True)
monthly.to_csv(OUT_DIR / "monthly_hvdc_transfer_NI_SI.csv", index=False)
log(f"Wrote monthly_hvdc_transfer_NI_SI.csv ({len(monthly)} rows)")

annual = wide.groupby("year")[["SI_to_NI_GWh", "NI_to_SI_GWh", "net_to_NI_GWh"]].sum().reset_index()
annual = annual.sort_values("year").reset_index(drop=True)

ann_gen = pd.read_csv(ROOT_OUT / "annual_emission_factor_NI_SI.csv")
ni_gen = ann_gen[ann_gen.island == "NI"].set_index("year")["total_gen_MWh"] / 1000
si_gen = ann_gen[ann_gen.island == "SI"].set_index("year")["total_gen_MWh"] / 1000
annual_ctx = annual.set_index("year").join(ni_gen.rename("NI_generation_GWh")).join(si_gen.rename("SI_generation_GWh"))
annual_ctx["net_to_NI_pct_of_NI_gen"] = annual_ctx["net_to_NI_GWh"] / annual_ctx["NI_generation_GWh"] * 100
annual_ctx["net_to_NI_pct_of_SI_gen"] = annual_ctx["net_to_NI_GWh"] / annual_ctx["SI_generation_GWh"] * 100
annual_ctx.to_csv(OUT_DIR / "annual_hvdc_transfer_NI_SI.csv")
log(f"Wrote annual_hvdc_transfer_NI_SI.csv ({len(annual_ctx)} rows, 2015-2025)")

log("\n=== Annual HVDC transfer summary (2015-2025) ===")
log(annual_ctx[["SI_to_NI_GWh", "NI_to_SI_GWh", "net_to_NI_GWh",
                 "net_to_NI_pct_of_NI_gen", "net_to_NI_pct_of_SI_gen"]].round(1).to_string())

total_north = annual["SI_to_NI_GWh"].sum()
total_south = annual["NI_to_SI_GWh"].sum()
log(f"\n2015-2025 totals: SI to NI = {total_north:,.0f} GWh, NI to SI = {total_south:,.0f} GWh, "
    f"net SI to NI = {total_north - total_south:,.0f} GWh "
    f"({(total_north-total_south)/ni_gen.sum()*100:.1f}% of NI's own generation, "
    f"{(total_north-total_south)/si_gen.sum()*100:.1f}% of SI's own generation)")

# Figure
fig, ax = plt.subplots(figsize=(13, 4.8))
ax.bar(monthly["period"], monthly["SI_to_NI_GWh"], width=20, color=NAVY, label="SI → NI (northward)")
ax.bar(monthly["period"], -monthly["NI_to_SI_GWh"], width=20, color=TEAL, label="NI → SI (southward)")
ax.plot(monthly["period"], monthly["net_to_NI_GWh"], color=GOLD, lw=1.6, label="Net transfer to NI")
ax.axhline(0, color="black", lw=0.8)
ax.set_ylabel("Energy transfer (GWh)")
ax.set_title("Monthly inter-island (HVDC) power transfer, 2015–2025")
ax.legend(loc="upper right", fontsize=8, ncol=3)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "monthly_hvdc_transfer_NI_SI.png", dpi=150)
log("\nWrote monthly_hvdc_transfer_NI_SI.png")

(OUT_DIR / "processing_log_hvdc.txt").write_text("\n".join(log_lines), encoding="utf-8")
log("Wrote: processing_log_hvdc.txt")
