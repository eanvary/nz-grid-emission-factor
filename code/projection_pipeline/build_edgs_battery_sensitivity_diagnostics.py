"""
Follow-up brief F: confirm Brief E's HVDC "worsening" (101/135 -> 104/135) against the
reconstruction's own known ~20 MW / 51 MW calibration noise floor, using a CONTINUOUS
violation-magnitude metric instead of a hard 1,200 MW threshold flag, and test Brief E's
proposed mechanism (demand-peak vs residual-peak divergence) directly rather than narrating
it.

This script reuses IDENTICAL reconstruction logic to build_edgs_battery_sensitivity.py (same
formulas, same inputs, NO recalibration of the known ~20/51 MW discrepancy - that noise floor
is used AS-IS, as the brief requires) but keeps the full hourly transfer series in memory to
compute:
  Step 1 - continuous violation magnitude: sum_t max(0, |transfer(t)| - 1200) MW, per
           scenario-year, both variants. Compared against the noise floor rescaled to the
           same annual-integrated units.
  Step 2 - demand-peak-hour vs residual-peak-hour divergence, correlated against the CHANGE
           in continuous violation magnitude (report-battery minus shipped-equivalent).

Standalone: reads only existing saved parquets, writes only new CSVs. Does not modify
build_edgs_dispatch.py, edgs_common.py, build_edgs_battery_sensitivity.py, or any shipped
output parquet.

Outputs: edgs_battery_hvdc_continuous_magnitude.csv, edgs_battery_mechanism_test.csv
"""
import os
import numpy as np
import pandas as pd

from edgs_common import ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, COMMODITY, log_factory

log, lines = log_factory()
HVDC_CAPACITY_MW = 1200.0
# TEMPLATE PARAMETERISATION (2026-08-12, Brief N): set EDGS_TEMPLATE_YEAR to re-derive
# against a different Assumption-1 shape template than the shipped 2021 central one.
TEMPLATE_YEAR = int(os.environ.get("EDGS_TEMPLATE_YEAR", "2021"))
SUFFIX = "" if TEMPLATE_YEAR == 2021 else f"_tmpl{TEMPLATE_YEAR}"
log(f"Template year: {TEMPLATE_YEAR} (suffix '{SUFFIX}')")

# Same report-battery function as build_edgs_battery_sensitivity.py (not recalibrated)
def report_battery_mw(scenario, year):
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
dsr_cap_map_shipped = {}
for sc in SCENARIOS:
    s = dsr_gem[dsr_gem.scenario == sc]
    for yr in YEARS:
        dsr_cap_map_shipped[(sc, yr)] = float(s[s.year <= yr]["capacity_mw"].sum())

dem_shape = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
dem_shape = dem_shape[dem_shape.template_year == TEMPLATE_YEAR]
ren_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_renewables.parquet")
ren_shape = ren_shape_all[ren_shape_all.template_year == TEMPLATE_YEAR]
# Solar real-shape fix (Brief T, adopted 2026-09-03) - same patch as build_edgs_dispatch.py
REAL_SOLAR_SHAPE = ren_shape_all[(ren_shape_all.template_year == 2024)
                                 & (ren_shape_all.island == "NI") & (ren_shape_all.fuel_std == "SOL")]
register = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")
merit = pd.read_parquet(OUT_DIR / "edgs_merit_order.parquet")

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


rows = []
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

        w_ni = map_weights(cal, dem_shape[dem_shape.island == "NI"][["month", "day", "hour", "weight"]])
        w_si = map_weights(cal, dem_shape[dem_shape.island == "SI"][["month", "day", "hour", "weight"]])
        demand_mwh = demand_twh * 1e6
        netgen_mwh = float(annual_gen.sum()) * 1000.0
        nat_demand_raw = demand_mwh * ni_share * w_ni + demand_mwh * (1 - ni_share) * w_si
        nat_shape = nat_demand_raw / nat_demand_raw.sum()
        nat_demand = nat_shape * netgen_mwh   # generation-level load (same as dispatch.py)

        residual_pre = np.clip(nat_demand - nat_ren, 0.0, None)

        # 1: demand-peak-hour vs residual-peak-hour divergence
        # "demand" here = the generation-level load series (nat_demand), the actual quantity
        # driving the transfer target in this pipeline; "residual" = demand minus renewables,
        # the quantity thermal/DSR actually respond to. Divergence measured in hours (0-23,
        # circular distance within the day, matching the daily peak-shave cycle's own scope).
        demand_peak_hr = int(np.argmax(nat_demand)) % 24
        residual_peak_hr = int(np.argmax(residual_pre)) % 24
        raw_diff = abs(demand_peak_hr - residual_peak_hr)
        hour_divergence = min(raw_diff, 24 - raw_diff)  # circular distance within a day

        dsr_ship = dsr_cap_map_shipped[(scenario, year)]
        dsr_rep = report_battery_mw(scenario, year)
        res_ship, dsr_series_ship = peak_shave(residual_pre, dsr_ship, H)
        res_rep, dsr_series_rep = peak_shave(residual_pre, dsr_rep, H)

        mplants = merit[(merit.scenario == scenario) & (merit.year == year)].sort_values("merit_rank")
        total_cap = mplants["capacity_mw"].sum()
        thermal_total_mwh = sum(float(annual_gen.get(c, 0.0)) for c in
                                ("Coal", "Natural gas", "Diesel", "LPG", "Fuel oil")) * 1000.0

        def transfer_series(residual, dsr_series_signed):
            th_shape_raw = np.clip(residual, 0.0, total_cap)
            th_shape = th_shape_raw / th_shape_raw.sum() if th_shape_raw.sum() > 0 else np.full(H, 1.0 / H)
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
            return gl_NI - g_NI

        tr_ship = transfer_series(res_ship, dsr_series_ship)
        tr_rep = transfer_series(res_rep, dsr_series_rep)

        # Continuous violation magnitude (MW-hours over 1200 MW, integrated)
        mag_ship = float(np.clip(np.abs(tr_ship) - HVDC_CAPACITY_MW, 0, None).sum())
        mag_rep = float(np.clip(np.abs(tr_rep) - HVDC_CAPACITY_MW, 0, None).sum())

        rows.append({
            "scenario": scenario, "year": year,
            "demand_peak_hr": demand_peak_hr, "residual_peak_hr": residual_peak_hr,
            "hour_divergence": hour_divergence,
            "max_transfer_mw_shipped": float(np.abs(tr_ship).max()),
            "max_transfer_mw_report": float(np.abs(tr_rep).max()),
            "continuous_mag_MWh_shipped": mag_ship,
            "continuous_mag_MWh_report": mag_rep,
            "continuous_mag_change": mag_rep - mag_ship,
        })
    log(f"  {scenario}: done")

df = pd.DataFrame(rows)
df.to_csv(OUT_DIR / f"edgs_battery_hvdc_continuous_magnitude{SUFFIX}.csv", index=False)

# Robustness verdict vs the known ~20/51 MW single-hour calibration discrepancy,
# rescaled to the same annual-integrated units for a fair comparison.
log("\n=== Step 1: continuous violation magnitude (MW-hours/yr over 1200 MW) ===")
tot_ship = df.continuous_mag_MWh_shipped.sum()
tot_rep = df.continuous_mag_MWh_report.sum()
tot_change = tot_rep - tot_ship
log(f"  Total across 135 scenario-years: shipped-equiv {tot_ship:,.0f} MWh  ->  "
    f"report-battery {tot_rep:,.0f} MWh  (change {tot_change:+,.0f} MWh, "
    f"{tot_change/tot_ship*100:+.1f}%)")

n_pos = (df.continuous_mag_change > 0).sum()
n_neg = (df.continuous_mag_change < 0).sum()
n_zero = (df.continuous_mag_change == 0).sum()
log(f"  Sign consistency: {n_pos}/135 worsen, {n_neg}/135 improve, {n_zero}/135 unchanged")

# Noise-floor rescale: the known ~20 MW mean / 51 MW max SINGLE-HOUR discrepancy, if it
# persisted across a comparable number of hours per scenario-year as the median violation
# duration actually observed, gives the annual-integrated noise floor for a fair comparison.
hours_per_sy_ship = ((df.continuous_mag_MWh_shipped > 0).sum())  # just for context
median_violating_hours = None
# Estimate typical violation-hours per scenario-year from Brief B/C output if available, else
# use a conservative single-hour-only floor (most conservative: assumes noise affects only 1
# hour, understating the noise floor) alongside a wider estimate using the known ~9,960 total
# flagged-hours / 135 scenario-years average duration from Brief C (~74 hours/scenario-year
# average among flagged years).
noise_floor_1hr_mean = 20.0     # MWh, single hour, mean discrepancy
noise_floor_1hr_max = 51.0      # MWh, single hour, max discrepancy
# Rescale using THIS template's own Brief C baseline flagged-hours/scenario-year among
# violators (2026-08-12: was hardcoded to Brief C's central-2021 9,961/103; now reads the
# matching {SUFFIX} sensitivity summary so the noise floor is template-consistent).
try:
    _hvdc = pd.read_csv(OUT_DIR / f"edgs_hvdc_sensitivity_summary{SUFFIX}.csv")
    _flagged = _hvdc[_hvdc.max_mw_baseline > HVDC_CAPACITY_MW]
    _total_flagged_hours = int(_flagged.n_hours_baseline.sum())
    _n_flagged_sy = len(_flagged)
    avg_violating_hours_baseline = _total_flagged_hours / _n_flagged_sy
    _noise_source = f"this template's own {_total_flagged_hours:,} total flagged hours / {_n_flagged_sy} flagged scenario-years"
except FileNotFoundError:
    avg_violating_hours_baseline = 9961 / 103  # fallback: Brief C's central-2021 figure
    _noise_source = "Brief C's central-2021 9,961 total flagged hours / 103 flagged scenario-years (fallback: this template's own edgs_hvdc_sensitivity_summary{SUFFIX}.csv not found)"
noise_floor_scaled_mean = noise_floor_1hr_mean * avg_violating_hours_baseline
noise_floor_scaled_max = noise_floor_1hr_max * avg_violating_hours_baseline
log(f"\n  Noise floor (single-hour calibration discrepancy): mean {noise_floor_1hr_mean} MWh, "
    f"max {noise_floor_1hr_max} MWh (per scenario-year, single hour).")
log(f"  Rescaled to annual-integrated units (x{avg_violating_hours_baseline:.1f} avg violating "
    f"hours/scenario-year, from {_noise_source}): "
    f"mean {noise_floor_scaled_mean:,.0f} MWh, max {noise_floor_scaled_max:,.0f} MWh PER "
    f"scenario-year (i.e. {noise_floor_scaled_mean*135:,.0f}-{noise_floor_scaled_max*135:,.0f} MWh "
    f"if this noise applied uniformly and in the SAME direction across all 135 scenario-years).")

per_sy_change_mean = df.continuous_mag_change.abs().mean()
log(f"\n  Actual mean |change| per scenario-year: {per_sy_change_mean:,.0f} MWh")
log(f"  Actual total change: {tot_change:+,.0f} MWh vs rescaled noise-floor range "
    f"{noise_floor_scaled_mean*135:,.0f}-{noise_floor_scaled_max*135:,.0f} MWh")

verdict_1 = "ROBUST" if (abs(tot_change) > noise_floor_scaled_max * 135 and n_pos > 2 * n_neg) else "NOT CLEARLY DISTINGUISHABLE FROM NOISE"
log(f"\n  VERDICT (Step 1): {verdict_1}")

# Mechanism test - correlate hour_divergence against continuous_mag_change
log("\n=== Step 2: mechanism test (demand-peak vs residual-peak divergence) ===")
log(f"  Hour divergence distribution: {df.hour_divergence.value_counts().sort_index().to_dict()}")
same_hour = df[df.hour_divergence == 0]
diff_hour = df[df.hour_divergence > 0]
log(f"  Same-hour scenario-years (n={len(same_hour)}): mean change {same_hour.continuous_mag_change.mean():+,.0f} MWh")
log(f"  Different-hour scenario-years (n={len(diff_hour)}): mean change {diff_hour.continuous_mag_change.mean():+,.0f} MWh")

corr = np.corrcoef(df.hour_divergence, df.continuous_mag_change)[0, 1] if df.hour_divergence.std() > 0 else np.nan
log(f"\n  Correlation (hour_divergence vs continuous_mag_change), all 135 scenario-years: {corr:.3f}")

if np.isfinite(corr) and corr > 0.3 and diff_hour.continuous_mag_change.mean() > same_hour.continuous_mag_change.mean():
    verdict_2 = "CONSISTENT WITH the proposed mechanism"
elif np.isfinite(corr) and abs(corr) < 0.15:
    verdict_2 = "NOT CONFIRMED - no meaningful correlation found"
else:
    verdict_2 = "PARTIALLY CONSISTENT - weak/mixed signal"
log(f"  VERDICT (Step 2): {verdict_2}")

df.to_csv(OUT_DIR / f"edgs_battery_mechanism_test{SUFFIX}.csv", index=False)
log(f"\nWrote edgs_battery_hvdc_continuous_magnitude{SUFFIX}.csv, edgs_battery_mechanism_test{SUFFIX}.csv "
    "(same file, both analyses)")
(OUT_DIR / f"processing_log_battery_diagnostics{SUFFIX}.txt").write_text("\n".join(lines), encoding="utf-8")
