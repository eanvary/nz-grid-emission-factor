"""
NI/SI CONSUMPTION-based monthly and annual emission factor database, 2015-2025.

REDESIGNED 2026-08-10 (systematic reliability assessment): this script previously
maintained its own full, independent copy of the raw EA/EMI ingestion pipeline
(local EA_EMI_raw/, EA data/ folders duplicating the root pipeline's), which meant
every bug found and fixed in the root generation/HVDC pipelines (SCD2 9999-year
timestamp overflow, DST fall-back TP49/TP50 drop, the 2021-2025-only curated HVDC
report) had to be independently re-discovered and re-fixed here -- and had NOT
been, until this pass. Rewritten to read the root pipeline's own already-fixed,
already-extended 2015-2025 outputs as its single source of truth instead of
re-deriving generation and HVDC transfer from raw files a second time. This
eliminates the duplicate-bug surface entirely: any future root-pipeline fix or
extension is inherited here automatically, with no separate re-implementation to
keep in sync. The old self-contained EA data/ and EA_EMI_raw/ copies in this
folder are no longer read by this script (left in place, unused, for now).

Inputs (root pipeline outputs, already validated -- see
DATA_QUALITY_ASSESSMENT_FRAMEWORK.md):
  output/monthly_emission_factor_NI_SI.csv   - generation-side EF by island/month
  output/annual_emission_factor_NI_SI.csv    - generation-side EF by island/year
  output/monthly_hvdc_transfer_NI_SI.csv (this folder) - inter-island transfer by month
  output/annual_hvdc_transfer_NI_SI.csv (this folder)  - inter-island transfer by year

Method (unchanged from the original design; see Consumption_EF_Worked_Example.docx
and NI_SI_Consumption_Emission_Factor_Methodology.docx for the full written
derivation):

1. Generation-side: taken directly from the root pipeline's own output.

2. Inter-island transfer: net_to_NI(t) = SI_to_NI(t) - NI_to_SI(t)
   [MWh, signed, positive = net flow to NI], taken directly from the root
   pipeline's raw-file-based HVDC output.

3. Energy balance ("apparent consumption" -- no metered T&D-loss or embedded-
   generation data is available; see Notes/Limitations in the written report):
     Consumption_NI(t) = Generation_NI(t) + net_to_NI(t)
     Consumption_SI(t) = Generation_SI(t) - net_to_NI(t)

4. Emissions balance (average-mix convention: electricity leaving an island via
   the HVDC link is assumed to carry that island's own generation-weighted EF
   for the period; this is the only assumption not directly observable in the
   data, and is stated explicitly):
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


# ---------------------------------------------------------------------------
# Step 1 — Generation-side, straight from the root pipeline's own output
# ---------------------------------------------------------------------------
gen_monthly = pd.read_csv(ROOT_OUT / "monthly_emission_factor_NI_SI.csv")
gen_annual = pd.read_csv(ROOT_OUT / "annual_emission_factor_NI_SI.csv")
log(f"Loaded generation-side EF: {len(gen_monthly)} monthly rows, {len(gen_annual)} annual rows "
    f"(years {gen_annual['year'].min()}-{gen_annual['year'].max()})")

# ---------------------------------------------------------------------------
# Step 2 — HVDC inter-island transfer, straight from the root pipeline's own
# raw-file-based output (GWh -> MWh for consistency with generation units)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Step 3 — Consumption balance
# ---------------------------------------------------------------------------
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

    out = out.reset_index()
    return out


monthly_cons = build_consumption(gen_monthly, hvdc_monthly, ["year", "month"])
monthly_cons["period"] = pd.to_datetime(monthly_cons[["year", "month"]].assign(day=1))
monthly_cons = monthly_cons.sort_values("period").reset_index(drop=True)

annual_cons = build_consumption(gen_annual, hvdc_annual, ["year"]).sort_values("year").reset_index(drop=True)

# ---------------------------------------------------------------------------
# Step 4 — Quality checks (energy- and emissions-conservation identities,
# which must hold exactly by construction; any discrepancy indicates a bug)
# ---------------------------------------------------------------------------
log("\n=== QUALITY CHECKS ===")
chk = annual_cons.copy()
chk["gen_total"] = chk["NI_generation_MWh"] + chk["SI_generation_MWh"]
chk["cons_total"] = chk["NI_consumption_MWh"] + chk["SI_consumption_MWh"]
max_energy_diff = (chk["gen_total"] - chk["cons_total"]).abs().max()
log(f"Energy conservation (sum of island generation == sum of island consumption, nationally): "
    f"max |diff| = {max_energy_diff:.6f} MWh (expect ~0)")

chk["co2_gen_total"] = chk["NI_CO2_generated_kg"] + chk["SI_CO2_generated_kg"]
chk["co2_cons_total"] = chk["NI_CO2_consumed_kg"] + chk["SI_CO2_consumed_kg"]
max_co2_diff = (chk["co2_gen_total"] - chk["co2_cons_total"]).abs().max()
log(f"Emissions conservation (sum of generated CO2 == sum of consumed CO2, nationally): "
    f"max |diff| = {max_co2_diff:.6f} kg (expect ~0)")

log(f"\nAnnual NI consumption-based EF: {annual_cons.set_index('year')['NI_EF_consumption'].round(1).to_dict()}")
log(f"Annual NI generation-based EF:  {annual_cons.set_index('year')['NI_EF_generation'].round(1).to_dict()}")
log(f"Annual SI consumption-based EF: {annual_cons.set_index('year')['SI_EF_consumption'].round(1).to_dict()}")
log(f"Annual SI generation-based EF:  {annual_cons.set_index('year')['SI_EF_generation'].round(1).to_dict()}")

for isl in ["NI", "SI"]:
    twh = annual_cons[f"{isl}_consumption_MWh"] / 1e6
    log(f"{isl} annual consumption (TWh): {dict(zip(annual_cons['year'], twh.round(2)))}")

log("\n=== NOTES (systematic HVDC/consumption review, 2026-08-10) ===")
log("1. Energy (MWh) is exactly resolution-independent at island level: summing this "
    "script's daily output to a month, or its monthly output to a year, matches this "
    "script's own coarser-resolution figure to machine precision (pure additive sums, "
    "no EF multiplication involved).")
log("2. Island-level CO2/EF is NOT exactly resolution-independent, BY DESIGN, not by "
    "error: the emissions-balance formula (Section 3.4 of the methodology note) "
    "multiplies transfer volume by THAT PERIOD'S OWN average EF_generation, so "
    "Sum_days(transfer_day x EF_day) != transfer_month x EF_month whenever transfer "
    "and EF co-vary within the period (they do, physically). Measured: NI CO2 "
    "consumed, daily-summed-to-month vs this script's own monthly figure, differs by "
    "mean 0.04%/max 0.39% of the monthly total across all 132 months (see "
    "validate_ef_database_2015_2025.py, checks H7a-c, for the full quantification "
    "and an algebraic proof that the NATIONAL total is unaffected -- only the NI/SI "
    "SPLIT of it is resolution-dependent). This is an inherent property of applying "
    "the average-mix assumption independently per resolution (as the methodology "
    "note's Section 4 explicitly specifies), not a bug to fix -- forcing exact "
    "cross-resolution CO2 reconciliation would require abandoning that "
    "independently-computed-per-resolution design.")

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
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
