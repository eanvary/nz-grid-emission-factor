"""
BDG2 real-data sensitivity test (script 2 of 4): build an empirical hourly load
"shape" per building from the real metered data, for use in the same
load-weighted decomposition method as the main (stylised-shape) assessment.

Key assumption, Southern Hemisphere calendar shift:
all 6 sample buildings are Northern Hemisphere (US/UK/Ireland). Their
seasonal pattern is what stylised shapes cannot capture at all. To line it
up with New Zealand's grid data, each building's calendar month is shifted
by 6 months when building the shape. BDG2 December/January (Northern
winter) maps to NZ June/July (Southern winter), and so on. This is a proxy
assumption, not a claim about real NZ building behaviour, and it is stated
here and in every downstream output.

Shape granularity: (nz_month, is_weekend, hour), averaged across both 2016
and 2017, rather than exact calendar dates. BDG2's 2016/2017 calendar does
not line up date-for-date with the NZ EDGS projection years (different
weekday offsets, different leap-year placement). The shape keeps the real
month-to-month (seasonal, weather-driven) and weekday/weekend structure
that the stylised shapes lack, at the cost of day-to-day granularity
within a month.
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"

log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

elec = pd.read_csv(TABLES / "sample_buildings_hourly_electricity_kwh.csv", parse_dates=["timestamp"])
BUILDINGS = [c for c in elec.columns if c != "timestamp"]
log(f"Buildings: {BUILDINGS}")

elec = elec.set_index("timestamp")
# interpolate short gaps (<=6h) linearly; leave longer gaps as NaN (excluded from shape averaging)
elec_interp = elec.interpolate(method="linear", limit=6, limit_direction="both")
n_still_missing = elec_interp[BUILDINGS].isna().sum()
log(f"\nRemaining missing after <=6h linear interpolation:\n{n_still_missing}")

elec_interp = elec_interp.reset_index()
elec_interp["month"] = elec_interp["timestamp"].dt.month
elec_interp["dow"] = elec_interp["timestamp"].dt.dayofweek
elec_interp["is_weekend"] = elec_interp["dow"] >= 5
elec_interp["hour"] = elec_interp["timestamp"].dt.hour

# Southern Hemisphere calendar shift: NZ_month = ((month + 5) % 12) + 1
elec_interp["nz_month"] = ((elec_interp["month"] + 5) % 12) + 1
log("\nHemisphere-shift check (BDG2 month to NZ month): "
    + ", ".join(f"{m} to {((m+5)%12)+1}" for m in range(1, 13)))

# Build empirical shape: mean kWh by (building, nz_month, is_weekend, hour)
shape_rows = []
for b in BUILDINGS:
    g = elec_interp[["nz_month", "is_weekend", "hour", b]].dropna()
    agg = g.groupby(["nz_month", "is_weekend", "hour"])[b].mean().reset_index()
    agg["building_id"] = b
    agg = agg.rename(columns={b: "mean_kwh"})
    shape_rows.append(agg)
shapes = pd.concat(shape_rows, ignore_index=True)

# Also build the sample-average shape (all 6 buildings pooled, each first
# normalised to its own annual total so no single building's absolute scale
# dominates the average). This is the headline "real shape" candidate.
norm_rows = []
for b in BUILDINGS:
    sub = shapes[shapes["building_id"] == b].copy()
    sub["norm_weight"] = sub["mean_kwh"] / sub["mean_kwh"].sum()
    norm_rows.append(sub)
shapes_norm = pd.concat(norm_rows, ignore_index=True)

avg_shape = (shapes_norm.groupby(["nz_month", "is_weekend", "hour"])["norm_weight"]
             .mean().reset_index())
avg_shape["norm_weight"] = avg_shape["norm_weight"] / avg_shape["norm_weight"].sum()
avg_shape["building_id"] = "SAMPLE_AVERAGE_6_BUILDINGS"

all_shapes = pd.concat([shapes_norm[["building_id", "nz_month", "is_weekend", "hour", "norm_weight"]],
                         avg_shape[["building_id", "nz_month", "is_weekend", "hour", "norm_weight"]]],
                        ignore_index=True)
all_shapes.to_csv(TABLES / "real_building_shapes_hemisphere_shifted.csv", index=False)
log(f"\nWrote real_building_shapes_hemisphere_shifted.csv ({len(all_shapes)} rows)")

# Sanity: seasonal pattern per building (mean weight by nz_month)
log("\n=== Mean normalised weight by NZ month, per building (seasonal signature) ===")
seasonal = all_shapes.groupby(["building_id", "nz_month"])["norm_weight"].sum().unstack("nz_month")
log(seasonal.round(4).to_string())

# Sanity: weekday and weekend contrast (does this look like a real office?)
log("\n=== Weekday and weekend mean hourly weight, per building ===")
wnd = all_shapes.groupby(["building_id", "is_weekend"])["norm_weight"].mean().unstack("is_weekend")
wnd.columns = ["weekday_mean", "weekend_mean"]
wnd["weekend_pct_of_weekday"] = 100 * wnd["weekend_mean"] / wnd["weekday_mean"]
log(wnd.round(6).to_string())

with open(ROOT / "logs" / "02_build_real_shapes_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log("\nDone.")
