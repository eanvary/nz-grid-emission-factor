"""
Cap the required inter-island transfer at real HVDC capacity and test whether NI's
consumption-side EF is understated in scenario-years where the required transfer exceeds
what the cable can physically carry.

Fidelity: required_transfer_to_NI(t) is reconstructed from the pipeline's own saved data
(edgs_hourly_generation.parquet's actual NI+SI generation, the real demand share/shape)
rather than by regenerating generation under a counterfactual assumption, as the
input-assumption sensitivities must. Module 7's transfer formula is
island_genload_NI(t) = nat_gen(t) x share(t), and nat_gen(t) = g_NI(t)+g_SI(t) is known
exactly from the saved table, so this reproduces Module 7's internal transfer series exactly
(max transfer for Reference/2035 matches Module 7's figure to the full precision printed).
The sensitivity scripts that regenerate generation can only approximate it.

Capacity cutover (stated interpretation, not a citation): every source found states only
"the early 2030s" for the 1200 to 1400 MW upgrade's completion; none gives a specific year.
This script uses 2032 as a reasoned midpoint of "the early 2030s" (commonly read as
2030-2033). It is not an MBIE/Transpower figure. A different year within "early 2030s"
would shift which scenario-years fall just either side of the cutover, but not the
qualitative finding.

Method: for each flagged hour (transfer_to_NI(t) > capacity(year)), shortfall(t) =
transfer_to_NI(t) - capacity(year). Spare NI thermal headroom is estimated as
total_NI_thermal_capacity(year) - already_dispatched_NI_thermal_generation(t). Both are
aggregate quantities: the pipeline reconciles thermal at fuel level, not plant level, so there
is no per-plant hourly dispatch to re-derive exactly. If spare exists, the shortfall goes to
the cheapest available merit-order plant(s) with estimated headroom
headroom_i(t) = capacity_i x (1 - utilisation_fraction(t)), where
utilisation_fraction(t) = already-dispatched thermal / total NI thermal capacity. Plants are
thus assumed loaded in proportion to the aggregate utilisation, a documented simplification of
"use the existing merit order to decide which plant absorbs it". CO2 uses that plant's own
heat-rate x MfE fuel factor (its marginal emission intensity). The pipeline's reconciled
average is not used, since this MW is by construction outside MBIE's reconciled annual total.
If spare is insufficient, the hour is flagged as an unserved-demand / reliability finding and
not folded into the emissions correction.

Standalone: reads only existing saved parquets, writes only new CSVs. Does not modify
build_edgs_dispatch.py, build_edgs_island_consumption.py, edgs_common.py, or any pipeline
output parquet.

Outputs: edgs_hvdc_capacity_correction_hours.csv   (every affected hour, served or unserved)
         edgs_hvdc_capacity_correction_summary.csv (per scenario-year: original and corrected NI consumption EF)
         edgs_hvdc_unserved_demand.csv              (reliability finding, if any hours are unservable)
"""
import numpy as np
import pandas as pd

from edgs_common import (map_weights, ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, THERMAL_COMMODITIES,
                         fuel_ef_kg_per_gj, log_factory)

log, lines = log_factory()
CUTOVER_YEAR = 2032  # stated interpretation of "the early 2030s"; see docstring
CAP_BEFORE, CAP_AFTER = 1200.0, 1400.0

targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
dem_shape = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
dem_shape = dem_shape[dem_shape.template_year == 2021]
gen = pd.read_parquet(OUT_DIR / "edgs_hourly_generation.parquet")
gen["year"] = pd.to_datetime(gen["datetime_hour"]).dt.year
ef = pd.read_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet")
ef["year"] = pd.to_datetime(ef["datetime_hour"]).dt.year
merit = pd.read_parquet(OUT_DIR / "edgs_merit_order.parquet")
register = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")

isd = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Island share of demand")
isd = isd[isd["Variable"] == "North Island share of national demand"]
ni_share_map = isd.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()


def capacity_for_year(year):
    return CAP_BEFORE if year < CUTOVER_YEAR else CAP_AFTER


def year_calendar(year):
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return pd.DataFrame({"datetime_hour": idx, "month": idx.month, "day": idx.day, "hour": idx.hour})


w_ni_base = dem_shape[dem_shape.island == "NI"][["month", "day", "hour", "weight"]]
w_si_base = dem_shape[dem_shape.island == "SI"][["month", "day", "hour", "weight"]]

hour_rows = []
summary_rows = []
unserved_rows = []

for scenario in SCENARIOS:
    merit_s = merit[merit.scenario == scenario]
    reg_s = register[register.scenario == scenario]
    for year in YEARS:
        cal = year_calendar(year)
        H = len(cal)
        dt = cal["datetime_hour"].to_numpy()
        ni_share = float(ni_share_map.get((scenario, year), 0.61))
        w_ni = map_weights(cal, w_ni_base)
        w_si = map_weights(cal, w_si_base)

        g = gen[(gen.scenario == scenario) & (gen.year == year)]
        g_NI = g[g.island == "NI"].groupby("datetime_hour")["generation_mwh"].sum().reindex(dt, fill_value=0.0).to_numpy()
        g_SI = g[g.island == "SI"].groupby("datetime_hour")["generation_mwh"].sum().reindex(dt, fill_value=0.0).to_numpy()
        nat_gen = g_NI + g_SI

        raw_ni = ni_share * w_ni; raw_si = (1 - ni_share) * w_si
        ssum = raw_ni + raw_si
        no_shape = ssum <= 0
        if no_shape.any():
            raw_ni = np.where(no_shape, ni_share, raw_ni)
            raw_si = np.where(no_shape, 1 - ni_share, raw_si)
            ssum = raw_ni + raw_si
        gl_NI = nat_gen * raw_ni / ssum
        transfer_to_NI = gl_NI - g_NI  # matches Module 7's internal series exactly

        cap = capacity_for_year(year)
        flagged_import = transfer_to_NI > cap       # NI wanted more import than the cable carries
        flagged_export = transfer_to_NI < -cap       # NI wanted to export more than the cable carries
        if not (flagged_import.any() or flagged_export.any()):
            continue  # scenario-year unaffected; leave untouched

        # Already-dispatched NI thermal generation and total NI thermal capacity, this hour/year
        gth = g[(g.island == "NI") & (g.fuel_commodity.isin(THERMAL_COMMODITIES))]
        thermal_dispatched = gth.groupby("datetime_hour")["generation_mwh"].sum().reindex(dt, fill_value=0.0).to_numpy()
        mplants = merit_s[merit_s.year == year].sort_values("merit_rank")
        total_thermal_cap = float(mplants["capacity_mw"].sum())

        efn = ef[(ef.scenario == scenario) & (ef.year == year) & (ef.island == "NI") & (ef.ef_basis == "generation")]
        genEF_NI = efn.set_index("datetime_hour")["emission_factor_kg_co2e_per_kwh"].reindex(dt, fill_value=0.0).to_numpy()
        efs = ef[(ef.scenario == scenario) & (ef.year == year) & (ef.island == "SI") & (ef.ef_basis == "generation")]
        genEF_SI = efs.set_index("datetime_hour")["emission_factor_kg_co2e_per_kwh"].reindex(dt, fill_value=0.0).to_numpy()

        # merit-order plant list with marginal EF (kg/MWh) for makeup dispatch, cheapest first
        plants = []
        for _, p in mplants.iterrows():
            hr = reg_s[(reg_s.year == year) & (reg_s.plant == p["plant"])]["heat_rate_gj_per_gwh"]
            hr = float(hr.iloc[0]) if len(hr) else np.nan
            marg_ef = fuel_ef_kg_per_gj(p["commodity"]) * (hr / 1000.0 if np.isfinite(hr) else 0.0)  # kg/MWh
            plants.append({"plant": p["plant"], "capacity_mw": float(p["capacity_mw"]), "marg_ef": marg_ef})

        orig_co2_sy = 0.0
        corr_co2_sy = 0.0
        makeup_mwh_sy = 0.0
        unserved_mwh_sy = 0.0
        n_import_flagged = int(flagged_import.sum())
        n_export_flagged = int(flagged_export.sum())

        for h in np.where(flagged_import)[0]:
            shortfall = transfer_to_NI[h] - cap
            util_frac = thermal_dispatched[h] / total_thermal_cap if total_thermal_cap > 0 else 1.0
            spare = total_thermal_cap - thermal_dispatched[h]

            orig_co2_h = g_NI[h] * genEF_NI[h] * 1000 + transfer_to_NI[h] * genEF_SI[h] * 1000  # kg
            orig_co2_sy += orig_co2_h

            if spare >= shortfall - 1e-6:
                # assign shortfall to cheapest plants with estimated headroom
                remaining = shortfall
                makeup_co2 = 0.0
                for p in plants:
                    headroom = p["capacity_mw"] * (1 - util_frac)
                    take = min(headroom, remaining)
                    if take > 0:
                        makeup_co2 += take * p["marg_ef"]  # kg
                        remaining -= take
                    if remaining <= 1e-9:
                        break
                corr_co2_h = g_NI[h] * genEF_NI[h] * 1000 + cap * genEF_SI[h] * 1000 + makeup_co2
                corr_co2_sy += corr_co2_h
                makeup_mwh_sy += shortfall
                hour_rows.append({"scenario": scenario, "year": year, "datetime_hour": dt[h],
                                  "type": "import_shortfall_SERVED", "required_transfer_mw": transfer_to_NI[h],
                                  "capacity_mw": cap, "shortfall_mw": shortfall, "spare_thermal_mw": spare,
                                  "orig_co2_kg": orig_co2_h, "corrected_co2_kg": corr_co2_h})
            else:
                corr_co2_sy += orig_co2_h  # not folded into the emissions correction; flagged separately
                unserved_mwh_sy += (shortfall - spare)
                unserved_rows.append({"scenario": scenario, "year": year, "datetime_hour": dt[h],
                                      "required_transfer_mw": transfer_to_NI[h], "capacity_mw": cap,
                                      "shortfall_mw": shortfall, "spare_thermal_mw": spare,
                                      "unserved_mw": shortfall - spare})
                hour_rows.append({"scenario": scenario, "year": year, "datetime_hour": dt[h],
                                  "type": "import_shortfall_UNSERVED", "required_transfer_mw": transfer_to_NI[h],
                                  "capacity_mw": cap, "shortfall_mw": shortfall, "spare_thermal_mw": spare,
                                  "orig_co2_kg": orig_co2_h, "corrected_co2_kg": orig_co2_h})

        for h in np.where(flagged_export)[0]:
            # NI wants to export more than the cable carries. This does not affect NI's own
            # consumption CO2/EF (NI's generation and consumption are unchanged). It is flagged
            # as a distinct SI-side curtailment signal, not folded into NI's EF.
            hour_rows.append({"scenario": scenario, "year": year, "datetime_hour": dt[h],
                              "type": "export_constrained_SI_curtailment", "required_transfer_mw": transfer_to_NI[h],
                              "capacity_mw": cap, "shortfall_mw": abs(transfer_to_NI[h]) - cap,
                              "spare_thermal_mw": np.nan, "orig_co2_kg": np.nan, "corrected_co2_kg": np.nan})

        # Recompute NI consumption EF for this scenario-year (affected hours corrected, rest untouched)
        t = targets[(targets.scenario == scenario) & (targets.year == year)]
        demand_twh = float(t[t.metric == "annual_demand"]["value"].iloc[0])
        island_demand_NI = demand_twh * 1e6 * ni_share * w_ni  # same denominator as Module 7

        # total-year CO2: unaffected hours use original CO2 as-is (g_NI*genEF_NI*1000 + transfer*genEF_SI*1000);
        # affected hours use orig_co2_sy / corr_co2_sy computed above (import side only; export-constrained
        # hours are NI-CO2-neutral by construction, so no adjustment needed there).
        all_hours_orig_co2 = (g_NI * genEF_NI * 1000 + transfer_to_NI * genEF_SI * 1000)
        total_orig_co2 = all_hours_orig_co2.sum()
        total_corr_co2 = total_orig_co2 - orig_co2_sy + corr_co2_sy  # swap in the corrected import-flagged hours

        orig_ef = total_orig_co2 / (island_demand_NI.sum() * 1000)
        corr_ef = total_corr_co2 / (island_demand_NI.sum() * 1000)

        summary_rows.append({
            "scenario": scenario, "year": year,
            "n_hours_import_flagged": n_import_flagged, "n_hours_export_flagged": n_export_flagged,
            "n_hours_unserved": len([r for r in unserved_rows if r["scenario"] == scenario and r["year"] == year]),
            "makeup_mwh": makeup_mwh_sy, "unserved_mwh": unserved_mwh_sy,
            "orig_NI_consumption_ef_kg_per_kwh": orig_ef, "corrected_NI_consumption_ef_kg_per_kwh": corr_ef,
            "diff_kg_per_kwh": corr_ef - orig_ef,
            "diff_pct": (corr_ef / orig_ef - 1) * 100 if orig_ef > 0 else np.nan,
        })
    log(f"  {scenario}: done")

hours_df = pd.DataFrame(hour_rows)
summary_df = pd.DataFrame(summary_rows)
unserved_df = pd.DataFrame(unserved_rows)

hours_df.to_csv(OUT_DIR / "edgs_hvdc_capacity_correction_hours.csv", index=False)
summary_df.to_csv(OUT_DIR / "edgs_hvdc_capacity_correction_summary.csv", index=False)
if len(unserved_df):
    unserved_df.to_csv(OUT_DIR / "edgs_hvdc_unserved_demand.csv", index=False)

log(f"\n=== Summary: {len(summary_df)} affected scenario-years (cap {CAP_BEFORE}/{CAP_AFTER} MW, cutover {CUTOVER_YEAR}) ===")
log(f"  Total import-flagged hours: {summary_df.n_hours_import_flagged.sum()}")
log(f"  Total export-flagged hours: {summary_df.n_hours_export_flagged.sum()}")
log(f"  Total unserved hours (reliability finding): {summary_df.n_hours_unserved.sum()}")
log(f"  Mean diff_pct across affected scenario-years: {summary_df.diff_pct.mean():.2f}%")
log(f"  Max diff_pct: {summary_df.diff_pct.max():.2f}% (scenario-year: "
    f"{summary_df.loc[summary_df.diff_pct.idxmax(), ['scenario','year']].to_dict()})")
log("\nMost-affected scenario-years (top 10 by diff_pct):")
log(summary_df.sort_values("diff_pct", ascending=False).head(10)[
    ["scenario", "year", "orig_NI_consumption_ef_kg_per_kwh", "corrected_NI_consumption_ef_kg_per_kwh", "diff_pct"]
].round(4).to_string(index=False))

if len(unserved_df):
    log(f"\n=== Reliability finding: {len(unserved_df)} hours where NI's thermal fleet cannot "
        f"cover the shortfall even at full output ===")
    log(unserved_df.groupby(["scenario", "year"]).size().rename("n_unserved_hours").reset_index()
        .sort_values("n_unserved_hours", ascending=False).head(15).to_string(index=False))
else:
    log("\nNo unserved-demand hours found: NI's thermal fleet has sufficient spare capacity "
        "in every affected hour.")

(OUT_DIR / "processing_log_hvdc_capacity_correction.txt").write_text("\n".join(lines), encoding="utf-8")
log("\nWrote edgs_hvdc_capacity_correction_hours.csv, edgs_hvdc_capacity_correction_summary.csv"
    + (", edgs_hvdc_unserved_demand.csv" if len(unserved_df) else ""))
