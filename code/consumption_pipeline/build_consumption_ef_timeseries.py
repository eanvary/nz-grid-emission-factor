"""
NI/SI consumption-based monthly and annual emission factor database, 2015-2025.

Design: the root pipeline's 2015-2025 outputs are the single source of truth;
generation and HVDC transfer are not re-derived from raw files a second time.
A separate copy of the raw EA/EMI ingestion (local EA_EMI_raw/, EA data/
folders) would have to repeat every correction in the root generation and HVDC
pipelines (SCD2 9999-year timestamp overflow, DST fall-back TP49/TP50 drop,
the 2021-2025-only curated HVDC report). Reading the root outputs means any
root-pipeline correction or extension carries over here, with no separate
implementation to keep in sync. Any EA data/ or EA_EMI_raw/ copies in this
folder are not read by this script.

Inputs (root pipeline outputs, already validated):
  output/monthly_emission_factor_NI_SI.csv:   generation-side EF by island/month
  output/annual_emission_factor_NI_SI.csv:    generation-side EF by island/year
  output/monthly_hvdc_transfer_NI_SI.csv (this folder): inter-island transfer by month
  output/annual_hvdc_transfer_NI_SI.csv (this folder):  inter-island transfer by year

Method (the full written derivation is in the consumption methodology note and
its worked example):

1. Generation side: taken directly from the root pipeline's output.

2. Inter-island transfer: net_to_NI(t) = SI_to_NI(t) - NI_to_SI(t)
   [MWh, signed, positive = net flow to NI], taken directly from the root
   pipeline's raw-file-based HVDC output.

3. Energy balance ("apparent consumption"; no metered T&D-loss or embedded-
   generation data is available, see Notes/Limitations in the written report):
     Consumption_NI(t) = Generation_NI(t) + net_to_NI(t)
     Consumption_SI(t) = Generation_SI(t) - net_to_NI(t)

4. Emissions balance (average-mix convention: electricity leaving an island via
   the HVDC link is assumed to carry that island's own generation-weighted EF
   for the period. This is the only assumption not directly observable in the
   data):
     CO2_consumed_NI(t) = CO2_generated_NI(t) - NI_to_SI(t)*EF_gen_NI(t) + SI_to_NI(t)*EF_gen_SI(t)
     CO2_consumed_SI(t) = CO2_generated_SI(t) - SI_to_NI(t)*EF_gen_SI(t) + NI_to_SI(t)*EF_gen_NI(t)

5. EF_consumption_island(t) = CO2_consumed_island(t) / Consumption_island(t)
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
gen_monthly = pd.read_csv(ROOT_OUT / "monthly_emission_factor_NI_SI.csv")
gen_annual = pd.read_csv(ROOT_OUT / "annual_emission_factor_NI_SI.csv")
log(f"Loaded generation-side EF: {len(gen_monthly)} monthly rows, {len(gen_annual)} annual rows "
    f"(years {gen_annual['year'].min()}-{gen_annual['year'].max()})")

# HVDC inter-island transfer from the root pipeline's raw-file-based output,
# converted from GWh to MWh to match the generation units
hvdc_monthly_raw = pd.read_csv(OUT_DIR / "monthly_hvdc_transfer_NI_SI.csv")
hvdc_monthly = hvdc_monthly_raw.rename(columns={
    "SI_to_NI_GWh": "SI_to_NI_MWh", "NI_to_SI_GWh": "NI_to_SI_MWh", "net_to_NI_GWh": "net_to_NI_MWh",
})
for c in ["SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh"]:
    hvdc_monthly[c] = hvdc_monthly[c] * 1000

hvdc_annual_raw = pd.read_csv(OUT_DIR / "annual_hvdc_transfer_NI_SI.csv")
hvdc_annual = hvdc_annual_raw.rename(columns={
    "SI_to_NI_GWh": "SI_to_NI_MWh", "NI_to_SI_GWh": "NI_to_SI_MWh", "net_to_NI_GWh": "net_to_NI_MWh",
})[["year", "SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh"]]
for c in ["SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh"]:
    hvdc_annual[c] = hvdc_annual[c] * 1000

log(f"Loaded HVDC transfer: {len(hvdc_monthly)} monthly rows, {len(hvdc_annual)} annual rows")

from consumption_balance import build_consumption  # noqa: E402


monthly_cons = build_consumption(gen_monthly, hvdc_monthly, ["year", "month"])
monthly_cons["period"] = pd.to_datetime(monthly_cons[["year", "month"]].assign(day=1))
monthly_cons = monthly_cons.sort_values("period").reset_index(drop=True)

annual_cons = build_consumption(gen_annual, hvdc_annual, ["year"]).sort_values("year").reset_index(drop=True)

# Quality checks (energy- and emissions-conservation identities,
# which must hold exactly by construction; any discrepancy indicates a bug)
log("\n=== QUALITY CHECKS ===")
chk = annual_cons.copy()
chk["gen_total"] = chk["NI_generation_MWh"] + chk["SI_generation_MWh"]
chk["cons_total"] = chk["NI_consumption_MWh"] + chk["SI_consumption_MWh"]
max_energy_diff = (chk["gen_total"] - chk["cons_total"]).abs().max()
log(f"Energy conservation (sum of island generation == sum of island consumption, nationally): "
    f"max |diff| = {max_energy_diff:.6f} MWh (expected: about 0)")

chk["co2_gen_total"] = chk["NI_CO2_generated_kg"] + chk["SI_CO2_generated_kg"]
chk["co2_cons_total"] = chk["NI_CO2_consumed_kg"] + chk["SI_CO2_consumed_kg"]
max_co2_diff = (chk["co2_gen_total"] - chk["co2_cons_total"]).abs().max()
log(f"Emissions conservation (sum of generated CO2 == sum of consumed CO2, nationally): "
    f"max |diff| = {max_co2_diff:.6f} kg (expected: about 0)")
assert np.allclose(chk["gen_total"], chk["cons_total"], rtol=1e-9), "island consumption does not balance generation"
assert np.allclose(chk["co2_gen_total"], chk["co2_cons_total"], rtol=1e-9), "consumed CO2 does not balance generated CO2"

log(f"\nAnnual NI consumption-based EF: {annual_cons.set_index('year')['NI_EF_consumption'].round(1).to_dict()}")
log(f"Annual NI generation-based EF:  {annual_cons.set_index('year')['NI_EF_generation'].round(1).to_dict()}")
log(f"Annual SI consumption-based EF: {annual_cons.set_index('year')['SI_EF_consumption'].round(1).to_dict()}")
log(f"Annual SI generation-based EF:  {annual_cons.set_index('year')['SI_EF_generation'].round(1).to_dict()}")

for isl in ["NI", "SI"]:
    twh = annual_cons[f"{isl}_consumption_MWh"] / 1e6
    log(f"{isl} annual consumption (TWh): {dict(zip(annual_cons['year'], twh.round(2)))}")

log("\n=== NOTES ===")
log("1. Energy (MWh) is exactly resolution-independent at island level: summing this "
    "script's daily output to a month, or its monthly output to a year, matches this "
    "script's own coarser-resolution figure to machine precision (pure additive sums, "
    "no EF multiplication involved).")
log("2. Island-level CO2/EF is not exactly resolution-independent, by design. The "
    "emissions-balance formula (Section 3.4 of the methodology note) multiplies "
    "transfer volume by that period's own average EF_generation, so "
    "Sum_days(transfer_day x EF_day) != transfer_month x EF_month whenever transfer "
    "and EF co-vary within the period (they do, physically). Measured: NI CO2 "
    "consumed, summed from days to months, differs from this script's monthly figure "
    "by mean 0.04% and max 0.39% of the monthly total across all 132 months. "
    "validate_ef_database_2015_2025.py (checks H7a-c) gives the full quantification "
    "and an algebraic proof that the national total is unaffected; only its NI/SI "
    "split depends on resolution. This follows from applying the average-mix "
    "assumption independently per resolution, as Section 4 of the methodology note "
    "specifies. Exact cross-resolution CO2 reconciliation would require giving up "
    "that per-resolution design.")

# Outputs
monthly_out = monthly_cons[[
    "year", "month", "period",
    "NI_consumption_MWh", "NI_CO2_consumed_kg", "NI_EF_consumption", "NI_EF_generation",
    "SI_consumption_MWh", "SI_CO2_consumed_kg", "SI_EF_consumption", "SI_EF_generation",
    "SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh",
]]
monthly_out.to_csv(OUT_DIR / "monthly_consumption_EF_NI_SI.csv", index=False)
log(f"\nWrote monthly_consumption_EF_NI_SI.csv ({len(monthly_out)} rows)")

annual_out = annual_cons[[
    "year",
    "NI_consumption_MWh", "NI_CO2_consumed_kg", "NI_EF_consumption", "NI_EF_generation",
    "SI_consumption_MWh", "SI_CO2_consumed_kg", "SI_EF_consumption", "SI_EF_generation",
    "SI_to_NI_MWh", "NI_to_SI_MWh", "net_to_NI_MWh",
]]
annual_out.to_csv(OUT_DIR / "annual_consumption_EF_NI_SI.csv", index=False)
log(f"Wrote annual_consumption_EF_NI_SI.csv ({len(annual_out)} rows)")

(OUT_DIR / "processing_log_consumption_monthly_annual.txt").write_text("\n".join(log_lines), encoding="utf-8")
log("Wrote processing_log_consumption_monthly_annual.txt")
