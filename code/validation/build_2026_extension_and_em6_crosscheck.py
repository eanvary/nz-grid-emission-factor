"""
Daily cross-check of national generation by fuel against em6, 2026.

em6 (Willie, EMS, by email) confirmed four public, free endpoints. The historical
carbon_intensity endpoint that the D2 check needs still returns 401 (subscription
required), but /free/price returns daily national generation-by-fuel MWh for a rolling
~185-day window, which started 2026-03-12 when this was run. The project's raw data
(EA_EMI_raw/*_Generation_MD.csv) ended 2025-12, so the two did not overlap. This script
builds the overlap:

1. The raw EA/EMI files for Jan-Aug 2026 are downloaded beforehand from the same public
   source the project already uses (emi.ea.govt.nz) and sit in EA_EMI_raw/ next to the
   2015-2025 files (140 months in total; the CSV schema was checked to be identical
   before use).
2. Builds a daily, national (NI+SI combined, matching the scope of em6's free data,
   which is national only) generation-by-fuel table for Jan-Aug 2026 only, using
   the pipeline's own generation reader and POC->island map
   (generation_pipeline/fuel_attribution.py: FuelAttribution.generation, poc_island_map),
   flagged fills included (none fall in 2026). Fuel is the metered EMI fuel code
   (standardised); the Huntly 1-4 coal/gas split is a factor attribution, not applied here,
   so Huntly Rankine output stays under CLG, matching em6's single "CG" class. Written to
   a separate validation-only file
   (generation_by_fuel_daily_2026.csv). The published output/*.csv files are not
   touched and stay scoped to 2015-2025.
3. Fetches em6's /free/price generation-by-fuel data for the same window, live.
4. Cross-checks the two, day by day and fuel by fuel, over the overlapping period.

This gives an external cross-check at daily resolution (em6's free endpoint is daily,
not half-hourly like the subscription one) without a paid subscription. It is partial
and covers a short window: it adds to Category D2 but does not replace the full
2015-2025 historical check, which still needs subscription access.
"""
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import FuelAttribution, poc_island_map  # noqa: E402

NEW_MONTHS = ["202601", "202602", "202603", "202604", "202605", "202606", "202607", "202608"]

# Build daily national generation-by-fuel for the 8 new months, using
# the pipeline's own generation reader (fuel_attribution.py) and
# POC->island map, not a local copy of them.
poc_island = poc_island_map()
fa = FuelAttribution()
gen = fa.generation(level="day", include_fills=True, months=NEW_MONTHS)
missing = sorted(set(NEW_MONTHS) - set(gen["trading_date"].dt.strftime("%Y%m")))
for m in missing:
    print(f"WARNING: {m}_Generation_MD.csv missing, skipping")
gen["island"] = gen["poc"].map(poc_island)
gen = gen[gen["island"].isin(["NI", "SI"])]
national_daily = gen.groupby(["trading_date", "fuel_std"])["gen_mwh"].sum().reset_index()
national_daily.to_csv(HERE / "generation_by_fuel_daily_2026.csv", index=False)
print(f"Built national daily generation-by-fuel for {len(NEW_MONTHS)} new months: "
      f"{national_daily.trading_date.min().date()} to {national_daily.trading_date.max().date()}, "
      f"{len(national_daily)} (date, fuel) rows -> generation_by_fuel_daily_2026.csv")

# Fetch em6's free generation-by-fuel data, live.
print("\nFetching em6 free/price generation-by-fuel data (live)...")
url = "https://api.em6.co.nz/ords/em6/data_api/free/price?grid_zone_id="
with urllib.request.urlopen(url, timeout=30) as resp:
    em6_raw = json.loads(resp.read().decode())

em6_rows = []
for item in em6_raw["items"]:
    td = pd.to_datetime(item["trading_date"]).normalize()
    for gt in item["generation_type"]:
        for key, val in gt.items():
            if key.endswith("_mwh"):
                fuel_em6 = key[:-4].upper()
                em6_rows.append({"trading_date": td, "fuel_em6": fuel_em6, "gen_mwh_em6": val})
em6_df = pd.DataFrame(em6_rows)
em6_df["trading_date"] = em6_df["trading_date"].dt.tz_localize(None)
em6_df.to_csv(HERE / "em6_free_generation_by_fuel_daily.csv", index=False)

# Day alignment (diagnosed in fix_em6_dayshift_and_rebuild_crosscheck.py): em6's
# trading_date is one calendar day earlier than this project's NZT trading-day
# convention for the same physical generation. A lag sweep shows it: HYD/WIN
# correlation rises from r=0.78/0.51 (no shift) to r=0.998/0.999 (+1 day shift).
# Applied here so a re-run of this live fetch is aligned; see that script's
# docstring for the diagnostic.
EM6_DAY_SHIFT = 1
em6_df["trading_date"] = em6_df["trading_date"] + pd.Timedelta(days=EM6_DAY_SHIFT)
print(f"Fetched em6 data: {em6_df.trading_date.min().date()} to {em6_df.trading_date.max().date()}, "
      f"{len(em6_raw['items'])} days -> em6_free_generation_by_fuel_daily.csv")

# em6 fuel codes -> this project's fuel_std (best mapping available; COG/LIQ/BAT have no
# direct analog in this project's FUEL_STD set, excluded from the cross-check rather than
# guessed at).
EM6_TO_PROJECT = {"GAS": "GAS", "CG": "CLG", "HYD": "HYD", "WIN": "WIN", "SOL": "SOL", "GEO": "GEO"}
em6_df["fuel_std"] = em6_df["fuel_em6"].map(EM6_TO_PROJECT)
em6_mapped = em6_df.dropna(subset=["fuel_std"])

# Cross-check on the overlapping window only.
overlap_start = max(national_daily.trading_date.min(), em6_mapped.trading_date.min())
overlap_end = min(national_daily.trading_date.max(), em6_mapped.trading_date.max())
print(f"\nOverlapping window: {overlap_start.date()} to {overlap_end.date()}")

if overlap_start > overlap_end:
    print("NO OVERLAP -- cross-check cannot run. Reporting this plainly, not forcing a comparison.")
else:
    ours = national_daily[(national_daily.trading_date >= overlap_start) & (national_daily.trading_date <= overlap_end)]
    theirs = em6_mapped[(em6_mapped.trading_date >= overlap_start) & (em6_mapped.trading_date <= overlap_end)]
    comp = ours.merge(theirs, on=["trading_date", "fuel_std"], how="inner", suffixes=("_ours", "_em6"))
    comp["diff_pct"] = (comp["gen_mwh"] - comp["gen_mwh_em6"]) / comp["gen_mwh_em6"] * 100
    comp.to_csv(HERE / "em6_crosscheck_overlap.csv", index=False)
    print(f"Matched {len(comp)} (date, fuel) rows in the overlap window.")
    print("\nPer-fuel comparison (mean daily MWh, this project vs. em6, over the overlap):")
    summary = comp.groupby("fuel_std").agg(
        n_days=("trading_date", "nunique"),
        ours_mean_mwh=("gen_mwh", "mean"),
        em6_mean_mwh=("gen_mwh_em6", "mean"),
        mean_abs_diff_pct=("diff_pct", lambda x: x.abs().mean()),
        corr=("gen_mwh", lambda x: np.nan),  # filled below
    )
    for fuel in summary.index:
        sub = comp[comp.fuel_std == fuel]
        summary.loc[fuel, "corr"] = sub["gen_mwh"].corr(sub["gen_mwh_em6"])
    print(summary.round(2).to_string())
    summary.to_csv(HERE / "em6_crosscheck_summary_by_fuel.csv")
