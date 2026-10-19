"""
Battery/BESS capacity sensitivity test (standalone, not a pipeline change). This script does
not modify build_edgs_dispatch.py, edgs_common.py, or any pipeline output parquet. It reads
only the pipeline's existing saved intermediates and reconstructs the dispatch
residual/peak-shave chain in parallel, swapping the DSR capacity input for MBIE's
report-narrative battery figures, for comparison only.

Background: neither MBIE workbook contains a battery/BESS capacity figure. The only
storage-adjacent quantity in the Excel data is 'Demand side response' (DSR), which Assumption
2 is anchored to (GEM build schedule, ~500 MW by 2050). The MBIE EDGS 2024 report PDF's
narrative (Table 4, p.22; prose p.27-28) states larger explicit grid-battery targets:
  - Reference / Growth / Constraint: 733 MW by 2029, no further stated growth (report gives
    no figure beyond 2029 for these three; Table 4 lists Growth/Constraint as "Reference").
  - Innovation / Environmental: "much greater BESS development over a longer time horizon,
    adding further generic BESS capacity to reach approximately 1,700 MW by 2049."
Only these two anchor figures (733 MW/2029, 1700 MW/2049) are stated anywhere in the 52-page
report (checked by full-text search, table extraction, and manual page review of the BESS
section and Table 4; no finer year-by-year breakdown exists in the source). The trajectory
between these anchors (and the 2024 starting point) is this script's own linear
interpolation, not an MBIE-stated figure. Only 2029 and 2049 (2050 for I/E, since no further
growth is stated after 1700 MW) should be read as MBIE-grounded; intermediate years carry
interpolation uncertainty.

Gap at the two MBIE-stated anchor points (vs the pipeline's Excel-sourced DSR capacity):
  2029: DSR 185-262 MW vs report 733 MW -> ratio 2.8-4.0x (all 5 scenarios)
  2049: DSR ~494-511 MW vs report 1700 MW (Innovation/Environmental only) -> ratio ~3.3-3.4x

The pipeline uses only the Excel-sourced DSR figure. This script sizes the effect of that
choice; it does not change it.

Outputs (output/edgs/, separate from the pipeline outputs):
  edgs_battery_gap_comparison.csv       DSR vs report battery, by scenario-year
  edgs_battery_sensitivity_peakshave.csv  peak-shave magnitude/timing, before/after
  edgs_battery_sensitivity_hvdc.csv     HVDC violation count/magnitude, before/after
  edgs_battery_sensitivity_ef.csv       EF hourly-shape change, before/after
"""
import os
import numpy as np
import pandas as pd

from edgs_common import ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, COMMODITY, log_factory

log, lines = log_factory()
HVDC_CAPACITY_MW = 1200.0
# Template year: set EDGS_TEMPLATE_YEAR to re-derive the shape-dependent reconstruction
# against a different Assumption-1 template. The DSR-vs-report capacity gap does not
# depend on the template.
TEMPLATE_YEAR = int(os.environ.get("EDGS_TEMPLATE_YEAR", "2021"))
SUFFIX = "" if TEMPLATE_YEAR == 2021 else f"_tmpl{TEMPLATE_YEAR}"
log(f"Template year: {TEMPLATE_YEAR} (suffix '{SUFFIX}')")

# Report-stated battery capacity (interpolated, labelled as such) vs pipeline DSR
def report_battery_mw(scenario, year):
    """MBIE report Table 4 + prose (p.22, p.27-28). Only 733 MW/2029 and 1700 MW/2049 (I/E
    only) are MBIE-stated; all other years are this script's own linear interpolation."""
    if scenario in ("Innovation", "Environmental"):
        if year <= 2029:
            return 733.0 * (year - 2024) / (2029 - 2024)
        if year <= 2049:
            return 733.0 + (1700.0 - 733.0) * (year - 2029) / (2049 - 2029)
        return 1700.0
    else:
        if year <= 2029:
            return 733.0 * (year - 2024) / (2029 - 2024)
        return 733.0


targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
gem = pd.read_parquet(OUT_DIR / "edgs_gem_build.parquet")
dsr_gem = gem[gem.commodity == "Demand side response"]
dsr_cap_map_pipeline = {}
for sc in SCENARIOS:
    s = dsr_gem[dsr_gem.scenario == sc]
    for yr in YEARS:
        dsr_cap_map_pipeline[(sc, yr)] = float(s[s.year <= yr]["capacity_mw"].sum())

gap_rows = []
for sc in SCENARIOS:
    for yr in YEARS:
        pipeline = dsr_cap_map_pipeline[(sc, yr)]
        report = report_battery_mw(sc, yr)
        gap_rows.append({"scenario": sc, "year": yr, "dsr_mw_pipeline": pipeline,
                         "report_battery_mw": report,
                         "ratio": (report / pipeline) if pipeline > 0 else np.nan})
gap_df = pd.DataFrame(gap_rows)
gap_df.to_csv(OUT_DIR / "edgs_battery_gap_comparison.csv", index=False)
log("=== Step 1: battery capacity gap (MBIE-stated anchor years) ===")
for yr in (2029, 2049):
    log(f"  {yr}:")
    log(gap_df[gap_df.year == yr][["scenario", "dsr_mw_pipeline", "report_battery_mw", "ratio"]]
        .round(2).to_string(index=False))

# Prerequisites for the residual/dispatch reconstruction (read-only, same sources as
# build_edgs_dispatch.py; not the same code path, but the same math, for comparison)
dem_shape = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
dem_shape = dem_shape[dem_shape.template_year == TEMPLATE_YEAR]
ren_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_renewables.parquet")
ren_shape = ren_shape_all[ren_shape_all.template_year == TEMPLATE_YEAR]
# Real 2024 NI solar shape where the template has none: same rule as build_edgs_dispatch.py,
# applied here too since this script recomputes renewables independently rather than reading
# the renewable rows of the pipeline's generation parquet.
REAL_SOLAR_SHAPE = ren_shape_all[(ren_shape_all.template_year == 2024)
                                 & (ren_shape_all.island == "NI") & (ren_shape_all.fuel_std == "SOL")]
register = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")
merit = pd.read_parquet(OUT_DIR / "edgs_merit_order.parquet")
ef_pipeline = pd.read_parquet(OUT_DIR / f"edgs_hourly_emission_factor{SUFFIX}.parquet")
gen_pipeline = pd.read_parquet(OUT_DIR / f"edgs_hourly_generation{SUFFIX}.parquet")
gen_pipeline["year"] = pd.to_datetime(gen_pipeline["datetime_hour"]).dt.year
ef_pipeline["year"] = pd.to_datetime(ef_pipeline["datetime_hour"]).dt.year

isd = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Island share of demand")
isd = isd[isd["Variable"] == "North Island share of national demand"]
ni_share_map = isd.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()

RENEWABLE_COMMODITIES = [c for c, (_, k) in COMMODITY.items() if k == "renewable"]
COMMODITY_TO_STD = {com: std for com, (std, _) in COMMODITY.items()}


def year_calendar(year):
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return pd.DataFrame({"datetime_hour": idx, "month": idx.month, "day": idx.day, "hour": idx.hour})


def map_weights(cal, wtab):
    m = cal.merge(wtab, on=["month", "day", "hour"], how="left")
    w = m["weight"].fillna(0.0).to_numpy()
    s = w.sum()
    return w / s if s > 0 else w


def island_capacity_share(scenario):
    r = register[register.scenario == scenario]
    cap = r.groupby(["year", "commodity", "island"])["capacity_mw"].sum().reset_index()
    tot = cap.groupby(["year", "commodity"])["capacity_mw"].transform("sum")
    cap["share"] = np.where(tot > 0, cap["capacity_mw"] / tot, np.nan)
    return cap.set_index(["year", "commodity", "island"])["share"].to_dict()


def peak_shave(residual_pre, dsr_mw, H):
    """Exact replica of build_edgs_dispatch.py's Assumption 2 daily peak-shave logic."""
    residual = residual_pre.copy()
    if dsr_mw > 0:
        ndays = H // 24
        base = residual[:ndays * 24].reshape(ndays, 24)
        hi = base.argmax(axis=1); lo = base.argmin(axis=1)
        rows_idx = np.arange(ndays)
        shift = np.minimum(dsr_mw, base[rows_idx, hi])
        base[rows_idx, hi] -= shift
        base[rows_idx, lo] += shift
    return residual, residual_pre - residual


# Per scenario-year: reconstruct residual_pre, run peak-shave under pipeline vs report dsr_mw
peakshave_rows = []
hvdc_rows = []
ef_rows = []

for scenario in SCENARIOS:
    cap_share = island_capacity_share(scenario)
    for year in YEARS:
        cal = year_calendar(year)
        H = len(cal)
        dt = cal["datetime_hour"].to_numpy()
        t = targets[(targets.scenario == scenario) & (targets.year == year)]
        annual_gen = t[t.metric == "net_generation"].set_index("commodity")["value"]
        demand_twh = float(t[t.metric == "annual_demand"]["value"].iloc[0])
        ni_share = float(ni_share_map.get((scenario, year), 0.61))

        # renewables (island totals) - same as dispatch.py
        island_ren_total = {"NI": np.zeros(H), "SI": np.zeros(H)}
        for com in RENEWABLE_COMMODITIES:
            gwh = float(annual_gen.get(com, 0.0))
            if gwh <= 0:
                continue
            std = COMMODITY_TO_STD[com]
            for isl in ("NI", "SI"):
                share = cap_share.get((year, com, isl), np.nan)
                if not np.isfinite(share) or share <= 0:
                    continue
                wtab = ren_shape[(ren_shape.island == isl) & (ren_shape.fuel_std == std)]
                if (len(wtab) == 0 or wtab["weight"].sum() == 0) and std == "SOL":
                    wtab = REAL_SOLAR_SHAPE
                elif len(wtab) == 0 or wtab["weight"].sum() == 0:
                    wtab = ren_shape[(ren_shape.island == "NI") & (ren_shape.fuel_std == std)]
                w = map_weights(cal, wtab[["month", "day", "hour", "weight"]]) if len(wtab) else np.full(H, 1.0 / H)
                island_ren_total[isl] += gwh * 1000.0 * share * w
        nat_ren = island_ren_total["NI"] + island_ren_total["SI"]

        # generation-level load - same as dispatch.py
        w_ni = map_weights(cal, dem_shape[dem_shape.island == "NI"][["month", "day", "hour", "weight"]])
        w_si = map_weights(cal, dem_shape[dem_shape.island == "SI"][["month", "day", "hour", "weight"]])
        demand_mwh = demand_twh * 1e6
        netgen_mwh = float(annual_gen.sum()) * 1000.0
        nat_demand_raw = demand_mwh * ni_share * w_ni + demand_mwh * (1 - ni_share) * w_si
        nat_shape = nat_demand_raw / nat_demand_raw.sum()
        nat_demand = nat_shape * netgen_mwh

        residual_pre = np.clip(nat_demand - nat_ren, 0.0, None)

        dsr_ship = dsr_cap_map_pipeline[(scenario, year)]
        dsr_rep = report_battery_mw(scenario, year)
        res_ship, dsr_series_ship = peak_shave(residual_pre, dsr_ship, H)
        res_rep, dsr_series_rep = peak_shave(residual_pre, dsr_rep, H)

        # 1: peak-shave magnitude/timing
        peak_hr_ship = int(np.argmax(dsr_series_ship))
        peak_hr_rep = int(np.argmax(dsr_series_rep))
        peakshave_rows.append({
            "scenario": scenario, "year": year,
            "dsr_mw_pipeline": dsr_ship, "dsr_mw_report": dsr_rep,
            "total_shaved_mwh_pipeline": float(np.clip(dsr_series_ship, 0, None).sum()),
            "total_shaved_mwh_report": float(np.clip(dsr_series_rep, 0, None).sum()),
            "worst_shave_hour_pipeline": peak_hr_ship, "worst_shave_hour_report": peak_hr_rep,
            "same_worst_hour": peak_hr_ship == peak_hr_rep,
        })

        # 2: HVDC transfer / capacity check, before vs after
        # thermal shape from each residual (same merit-order-capacity-clip logic as dispatch.py)
        mplants = merit[(merit.scenario == scenario) & (merit.year == year)].sort_values("merit_rank")
        total_cap = mplants["capacity_mw"].sum()

        def thermal_gen_and_transfer(residual, dsr_series_signed):
            th_shape_raw = np.clip(residual, 0.0, total_cap)
            th_shape = th_shape_raw / th_shape_raw.sum() if th_shape_raw.sum() > 0 else np.full(H, 1.0 / H)
            thermal_total_mwh = sum(float(annual_gen.get(c, 0.0)) for c in
                                    ("Coal", "Natural gas", "Diesel", "LPG", "Fuel oil")) * 1000.0
            # NI "generation" for the transfer/EF calc must include the DSR net series as its
            # own explicit term (matching the pipeline's convention: DSR is a separate row in
            # edgs_hourly_generation.parquet, summed into island NI generation). Letting DSR
            # only reshape thermal via the residual is not enough; DSR's discharge/charge is
            # itself extra effective NI supply/demand at that hour. Without this term the
            # reconstructed baseline flags 4 fewer boundary-case scenario-years than the
            # pipeline's 103/135.
            g_NI = island_ren_total["NI"] + thermal_total_mwh * th_shape + dsr_series_signed
            g_SI = island_ren_total["SI"]
            nat_gen = g_NI + g_SI
            raw_ni = ni_share * w_ni; raw_si = (1 - ni_share) * w_si
            ssum = raw_ni + raw_si
            no_shape = ssum <= 0
            if no_shape.any():
                raw_ni = np.where(no_shape, ni_share, raw_ni)
                raw_si = np.where(no_shape, 1 - ni_share, raw_si)
                ssum = raw_ni + raw_si
            gl_NI = nat_gen * raw_ni / ssum
            return g_NI, g_SI, gl_NI - g_NI

        gNI_ship, gSI_ship, tr_ship = thermal_gen_and_transfer(res_ship, dsr_series_ship)
        gNI_rep, gSI_rep, tr_rep = thermal_gen_and_transfer(res_rep, dsr_series_rep)
        hvdc_rows.append({
            "scenario": scenario, "year": year,
            "max_transfer_mw_pipeline": float(np.abs(tr_ship).max()),
            "max_transfer_mw_report": float(np.abs(tr_rep).max()),
            "n_hours_violate_pipeline": int((np.abs(tr_ship) > HVDC_CAPACITY_MW).sum()),
            "n_hours_violate_report": int((np.abs(tr_rep) > HVDC_CAPACITY_MW).sum()),
        })

        # 3: EF hourly shape, before vs after
        mfe_thermal_co2_ship = None  # placeholder; use ratio of thermal MWh reshaping as EF proxy
        # Since combustion CO2 per fuel = MBIE fuel-use x MfE, distributed by the same thermal
        # shape, the CO2 profile reshapes identically to the thermal generation profile. The
        # EF hourly shape change is therefore captured by comparing the NI generation-side EF
        # implied by re-shaping the pipeline's combustion CO2 total over the new thermal shape.
        efn = ef_pipeline[(ef_pipeline.scenario == scenario) & (ef_pipeline.year == year)
                        & (ef_pipeline.island == "NI") & (ef_pipeline.ef_basis == "generation")]
        efn = efn.set_index("datetime_hour")["emission_factor_kg_co2e_per_kwh"].reindex(dt, fill_value=0.0).to_numpy()
        gn_ship_actual = gen_pipeline[(gen_pipeline.scenario == scenario) & (gen_pipeline.year == year)
                                     & (gen_pipeline.island == "NI")].groupby("datetime_hour")["generation_mwh"].sum().reindex(dt, fill_value=0.0).to_numpy()
        co2_ship_actual = efn * gn_ship_actual * 1000.0  # kg, pipeline baseline
        total_co2 = co2_ship_actual.sum()
        # re-shape total CO2 over the report-battery thermal shape (same total, new hourly pattern)
        th_shape_ship = np.clip(res_ship, 0.0, total_cap); th_shape_ship = th_shape_ship / th_shape_ship.sum() if th_shape_ship.sum() > 0 else np.full(H, 1.0 / H)
        th_shape_rep = np.clip(res_rep, 0.0, total_cap); th_shape_rep = th_shape_rep / th_shape_rep.sum() if th_shape_rep.sum() > 0 else np.full(H, 1.0 / H)
        co2_report_reshaped = total_co2 * th_shape_rep
        ef_report_reshaped = np.where(gNI_rep > 0, co2_report_reshaped / (gNI_rep * 1000.0), 0.0)
        mad = np.abs(ef_report_reshaped - efn).mean()
        ef_rows.append({"scenario": scenario, "year": year,
                        "mean_abs_hourly_EF_diff_kg_per_kwh": mad,
                        "peak_hour_EF_pipeline": float(efn[np.argmax(res_ship)]) if H else np.nan,
                        "peak_hour_EF_report": float(ef_report_reshaped[np.argmax(res_ship)]) if H else np.nan})
    log(f"  {scenario}: done")

pk = pd.DataFrame(peakshave_rows)
pk.to_csv(OUT_DIR / f"edgs_battery_sensitivity_peakshave{SUFFIX}.csv", index=False)
hv = pd.DataFrame(hvdc_rows)
hv.to_csv(OUT_DIR / f"edgs_battery_sensitivity_hvdc{SUFFIX}.csv", index=False)
efd = pd.DataFrame(ef_rows)
efd.to_csv(OUT_DIR / f"edgs_battery_sensitivity_ef{SUFFIX}.csv", index=False)

# Summary
log("\n=== Step 3.1: peak-shaving magnitude (total MWh/yr shaved, national) ===")
log(f"  Total shaved, pipeline DSR: {pk.total_shaved_mwh_pipeline.sum()/1e6:.2f} TWh/yr-equiv (135 scenario-years)")
log(f"  Total shaved, report battery: {pk.total_shaved_mwh_report.sum()/1e6:.2f} TWh/yr-equiv")
log(f"  Ratio: {pk.total_shaved_mwh_report.sum()/pk.total_shaved_mwh_pipeline.sum():.2f}x")
log(f"  Worst-shave hour changes in {(~pk.same_worst_hour).sum()}/135 scenario-years under the larger assumption")

log("\n=== HVDC capacity violation, pipeline DSR against report battery ===")
n_ship = (hv.max_transfer_mw_pipeline > HVDC_CAPACITY_MW).sum()
n_rep = (hv.max_transfer_mw_report > HVDC_CAPACITY_MW).sum()
log(f"  Scenario-years flagged: pipeline {n_ship}/135  ->  report-battery {n_rep}/135")
log(f"  Max transfer overall: pipeline {hv.max_transfer_mw_pipeline.max():.0f} MW  ->  "
    f"report-battery {hv.max_transfer_mw_report.max():.0f} MW")

log("\n=== Step 3.3: EF hourly shape change ===")
log(f"  Mean abs hourly EF diff (national NI, all 135 scenario-years): "
    f"{efd.mean_abs_hourly_EF_diff_kg_per_kwh.mean():.5f} kg/kWh")
log(f"  Peak-shave-hour EF: pipeline mean {efd.peak_hour_EF_pipeline.mean():.4f} kg/kWh -> "
    f"report-battery mean {efd.peak_hour_EF_report.mean():.4f} kg/kWh")

log(f"\nWrote edgs_battery_gap_comparison.csv, edgs_battery_sensitivity_peakshave{SUFFIX}.csv, "
    f"edgs_battery_sensitivity_hvdc{SUFFIX}.csv, edgs_battery_sensitivity_ef{SUFFIX}.csv")
(OUT_DIR / f"processing_log_battery_sensitivity{SUFFIX}.txt").write_text("\n".join(lines), encoding="utf-8")
