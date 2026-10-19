"""
NI/SI CONSUMPTION-based DAILY and HOURLY emission factor database, 2015-2025.
Same method as build_consumption_ef_timeseries.py (see that file's docstring
for the full methodology and for why it reads the root pipeline's outputs).

Reads the root pipeline's 2015-2025 daily/hourly outputs directly rather than
keeping a second copy of the raw-file ingestion logic, so fixes made there
(for example the SCD2 9999-year timestamp overflow and the DST fall-back
TP49/TP50 handling) apply here too.

Inputs (root pipeline outputs, already validated):
  output/daily_emission_factor_NI_SI.csv    - generation-side EF, daily
  output/hourly_emission_factor_NI_SI.csv   - generation-side EF, hourly
  output/daily_hvdc_transfer_NI_SI.csv (this folder)  - inter-island transfer, daily
  output/hourly_hvdc_transfer_NI_SI.csv (this folder) - inter-island transfer, hourly
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
ROOT_OUT = ROOT.parent / "output"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(str(msg))


# Generation-side, straight from the root pipeline's own output
gen_daily = pd.read_csv(ROOT_OUT / "daily_emission_factor_NI_SI.csv", parse_dates=["date"])
gen_hourly = pd.read_csv(ROOT_OUT / "hourly_emission_factor_NI_SI.csv", parse_dates=["date", "datetime"])
log(f"Loaded generation-side EF: {len(gen_daily)} daily island-rows, {len(gen_hourly)} hourly island-rows")

# HVDC transfer, straight from the root pipeline's own raw-file-based output
# (MWh already; no unit conversion needed, unlike the monthly/annual GWh files)
hvdc_daily = pd.read_csv(OUT_DIR / "daily_hvdc_transfer_NI_SI.csv", parse_dates=["date"])
hvdc_daily = hvdc_daily.rename(columns={
    "SI_to_NI_GWh": "SI_to_NI_MWh", "NI_to_SI_GWh": "NI_to_SI_MWh", "net_to_NI_GWh": "net_to_NI_MWh",
})
for c in ["SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh"]:
    hvdc_daily[c] = hvdc_daily[c] * 1000

hvdc_hourly = pd.read_csv(OUT_DIR / "hourly_hvdc_transfer_NI_SI.csv", parse_dates=["date", "datetime"])
log(f"Loaded HVDC transfer: {len(hvdc_daily)} daily rows, {len(hvdc_hourly)} hourly rows")


# Consumption balance (identical formulas to the monthly/annual script)
def build_consumption(gen_df, hvdc_df, group_keys):
    ni = gen_df[gen_df.island == "NI"].set_index(group_keys)
    si = gen_df[gen_df.island == "SI"].set_index(group_keys)
    h = hvdc_df.set_index(group_keys)

    idx = ni.index.union(si.index).union(h.index)
    ni = ni.reindex(idx, fill_value=0.0)
    si = si.reindex(idx, fill_value=0.0)
    h = h.reindex(idx, fill_value=0.0)

    out = pd.DataFrame(index=idx)
    out["NI_generation_MWh"] = ni["total_gen_MWh"]
    out["NI_CO2_generated_kg"] = ni["total_CO2_kg"]
    out["NI_EF_generation"] = (ni["total_CO2_kg"] / ni["total_gen_MWh"]).replace([np.inf, -np.inf], np.nan)
    out["SI_generation_MWh"] = si["total_gen_MWh"]
    out["SI_CO2_generated_kg"] = si["total_CO2_kg"]
    out["SI_EF_generation"] = (si["total_CO2_kg"] / si["total_gen_MWh"]).replace([np.inf, -np.inf], np.nan)
    out["SI_to_NI_MWh"] = h["SI_to_NI_MWh"]
    out["NI_to_SI_MWh"] = h["NI_to_SI_MWh"]
    out["net_to_NI_MWh"] = h["net_to_NI_MWh"]

    out["NI_consumption_MWh"] = out["NI_generation_MWh"] + out["net_to_NI_MWh"]
    out["SI_consumption_MWh"] = out["SI_generation_MWh"] - out["net_to_NI_MWh"]

    out["NI_CO2_consumed_kg"] = (
        out["NI_CO2_generated_kg"] - out["NI_to_SI_MWh"] * out["NI_EF_generation"]
        + out["SI_to_NI_MWh"] * out["SI_EF_generation"]
    )
    out["SI_CO2_consumed_kg"] = (
        out["SI_CO2_generated_kg"] - out["SI_to_NI_MWh"] * out["SI_EF_generation"]
        + out["NI_to_SI_MWh"] * out["NI_EF_generation"]
    )
    out["NI_EF_consumption"] = out["NI_CO2_consumed_kg"] / out["NI_consumption_MWh"]
    out["SI_EF_consumption"] = out["SI_CO2_consumed_kg"] / out["SI_consumption_MWh"]
    return out.reset_index()


daily_cons = build_consumption(gen_daily, hvdc_daily, ["date"]).sort_values("date").reset_index(drop=True)

gen_hourly_k = gen_hourly[["island", "date", "hour", "total_gen_MWh", "total_CO2_kg"]]
hvdc_hourly_k = hvdc_hourly[["date", "hour", "SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh"]]
hourly_cons = build_consumption(gen_hourly_k, hvdc_hourly_k, ["date", "hour"])
hourly_cons["datetime"] = hourly_cons["date"] + pd.to_timedelta(hourly_cons["hour"], unit="h")
hourly_cons = hourly_cons.sort_values("datetime").reset_index(drop=True)

# Quality checks
log("\n=== QUALITY CHECKS ===")
for name, d in [("daily", daily_cons), ("hourly", hourly_cons)]:
    gen_total = d["NI_generation_MWh"] + d["SI_generation_MWh"]
    cons_total = d["NI_consumption_MWh"] + d["SI_consumption_MWh"]
    co2_gen_total = d["NI_CO2_generated_kg"] + d["SI_CO2_generated_kg"]
    co2_cons_total = d["NI_CO2_consumed_kg"] + d["SI_CO2_consumed_kg"]
    log(f"{name}: max |energy diff| = {(gen_total - cons_total).abs().max():.6f} MWh, "
        f"max |CO2 diff| = {(co2_gen_total - co2_cons_total).abs().max():.6f} kg (both expect ~0)")

daily_to_hourly = (
    hourly_cons.groupby(hourly_cons["date"])[["NI_consumption_MWh", "SI_consumption_MWh"]].sum()
)
chk = daily_to_hourly.join(daily_cons.set_index("date")[["NI_consumption_MWh", "SI_consumption_MWh"]],
                            lsuffix="_h", rsuffix="_d")
max_h2d = (chk["NI_consumption_MWh_h"] - chk["NI_consumption_MWh_d"]).abs().max()
log(f"Hourly consumption sums to daily exactly: max |NI diff| = {max_h2d:.6f} MWh (expect ~0)")

# Outputs
daily_out = daily_cons[[
    "date", "NI_consumption_MWh", "NI_CO2_consumed_kg", "NI_EF_consumption", "NI_EF_generation",
    "SI_consumption_MWh", "SI_CO2_consumed_kg", "SI_EF_consumption", "SI_EF_generation",
    "SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh",
]]
daily_out.to_csv(OUT_DIR / "daily_consumption_EF_NI_SI.csv", index=False)
log(f"\nWrote daily_consumption_EF_NI_SI.csv ({len(daily_out)} rows)")

hourly_out = hourly_cons[[
    "date", "hour", "datetime", "NI_consumption_MWh", "NI_CO2_consumed_kg", "NI_EF_consumption", "NI_EF_generation",
    "SI_consumption_MWh", "SI_CO2_consumed_kg", "SI_EF_consumption", "SI_EF_generation",
    "SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh",
]]
hourly_out.to_csv(OUT_DIR / "hourly_consumption_EF_NI_SI.csv", index=False)
log(f"Wrote hourly_consumption_EF_NI_SI.csv ({len(hourly_out)} rows)")

(OUT_DIR / "processing_log_consumption_daily_hourly.txt").write_text("\n".join(log_lines), encoding="utf-8")
log("Wrote processing_log_consumption_daily_hourly.txt")
