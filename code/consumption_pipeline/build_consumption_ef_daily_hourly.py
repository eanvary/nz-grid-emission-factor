"""
NI/SI consumption-based daily and hourly emission factor database, 2015-2025.
Same method as build_consumption_ef_timeseries.py (its docstring gives the
method and the reason for reading the root pipeline's outputs).

The root pipeline's 2015-2025 daily and hourly outputs are read directly, with
no second copy of the raw-file ingestion logic. The root handling of the SCD2
9999-year timestamp overflow and of the DST fall-back TP49/TP50 therefore
applies here too.

Inputs (root pipeline outputs, already validated):
  output/daily_emission_factor_NI_SI.csv:    generation-side EF, daily
  output/hourly_emission_factor_NI_SI.csv:   generation-side EF, hourly
  output/daily_hvdc_transfer_NI_SI.csv (this folder):  inter-island transfer, daily
  output/hourly_hvdc_transfer_NI_SI.csv (this folder): inter-island transfer, hourly
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


# Generation side, read from the root pipeline's output
gen_daily = pd.read_csv(ROOT_OUT / "daily_emission_factor_NI_SI.csv", parse_dates=["date"])
gen_hourly = pd.read_csv(ROOT_OUT / "hourly_emission_factor_NI_SI.csv", parse_dates=["date", "datetime"])
log(f"Loaded generation-side EF: {len(gen_daily)} daily island-rows, {len(gen_hourly)} hourly island-rows")

# HVDC transfer from the root pipeline's raw-file-based output. These files are
# in MWh, so no unit conversion is needed (the monthly and annual files are in GWh).
hvdc_daily = pd.read_csv(OUT_DIR / "daily_hvdc_transfer_NI_SI.csv", parse_dates=["date"])
hvdc_daily = hvdc_daily.rename(columns={
    "SI_to_NI_GWh": "SI_to_NI_MWh", "NI_to_SI_GWh": "NI_to_SI_MWh", "net_to_NI_GWh": "net_to_NI_MWh",
})
for c in ["SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh"]:
    hvdc_daily[c] = hvdc_daily[c] * 1000

hvdc_hourly = pd.read_csv(OUT_DIR / "hourly_hvdc_transfer_NI_SI.csv", parse_dates=["date", "datetime"])
log(f"Loaded HVDC transfer: {len(hvdc_daily)} daily rows, {len(hvdc_hourly)} hourly rows")


from consumption_balance import build_consumption  # noqa: E402


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
        f"max |CO2 diff| = {(co2_gen_total - co2_cons_total).abs().max():.6f} kg (both expected: about 0)")
    assert np.allclose(gen_total, cons_total, rtol=1e-9), f"{name}: island consumption does not balance generation"
    assert np.allclose(co2_gen_total, co2_cons_total, rtol=1e-9), f"{name}: consumed CO2 does not balance generated CO2"

daily_to_hourly = (
    hourly_cons.groupby(hourly_cons["date"])[["NI_consumption_MWh", "SI_consumption_MWh"]].sum()
)
chk = daily_to_hourly.join(daily_cons.set_index("date")[["NI_consumption_MWh", "SI_consumption_MWh"]],
                            lsuffix="_h", rsuffix="_d")
max_h2d = (chk["NI_consumption_MWh_h"] - chk["NI_consumption_MWh_d"]).abs().max()
log(f"Hourly consumption sums to daily exactly: max |NI diff| = {max_h2d:.6f} MWh (expected: about 0)")
assert len(chk) == len(daily_cons), "hourly consumption is missing days that the daily output has"
assert np.allclose(chk["NI_consumption_MWh_h"], chk["NI_consumption_MWh_d"], rtol=1e-9), "hourly consumption does not sum to daily"

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
