"""
Follow-up brief T — replace the FLAT solar-shape fallback with the real observed 2024 NI solar
diurnal/seasonal shape, as a STANDALONE SENSITIVITY TEST. Standalone: reads only existing
shipped parquets, writes only new CSVs. Does not modify build_edgs_dispatch.py, edgs_common.py,
or any shipped output parquet.

BACKGROUND: EA/EMI raw data carries no Solar fuel code before 2024, so the central (2021) and
median (2017) Assumption-1 templates have ZERO solar rows in edgs_shape_renewables.parquet
(verified). build_edgs_dispatch.py's own fallback logic (Step A2) therefore spreads solar
generation FLAT across all 24 hours for every scenario-year of the shipped pipeline. MBIE's own
solar methodology (EDGS 2024 report, p.25-28) gives no help here either: it converts distributed-
PV capacity straight to annual GWh via one flat 14.5% capacity factor, with no diurnal or
seasonal profile of its own to borrow. Real NZ solar generation shape (template_year=2024,
island=NI) DOES exist in edgs_shape_renewables.parquet (8,784 real hourly weights, confirmed
non-flat) but is unused by every scenario-year, because it postdates the chosen template years.

This is a MATERIAL gap, not cosmetic: MBIE's own solar GWh grows 5-16x by 2050 across scenarios
(823 GWh in 2024 -> up to 13,706 GWh in 2050), so an increasingly large annual quantity is being
smeared uniformly across 24 hours instead of concentrated in daylight hours.

DESIGN (agreed with user before building):
  1. Future solar GAIN: untouched - MBIE's own annual solar GWh per scenario-year, unchanged.
  2. Daylight-length / diurnal-seasonal SHAPE: the real observed 2024 NI hourly solar generation
     shape (edgs_shape_renewables.parquet, template_year=2024, island=NI), applied in place of
     the flat fallback for the CENTRAL (2021) template. This is real NZ observed data (already
     encodes NZ's actual seasonal daylight swing + real cloud-cover effects), not a synthetic
     sun-position model - the strongest available source, no external citation needed.
  3. Daylight length itself does not get a "future" trend (astronomically fixed) - only the
     volume riding on the fixed shape grows, via (1), unchanged from the shipped pipeline.
  4. South Island: no real SI solar shape exists in any template. The real NI shape is applied
     to SI too (same convention as the pipeline's own existing island-fallback logic), explicitly
     flagged - a disclosed limitation (SI's actual daylight swing is more extreme than NI's,
     understated here), not a silent one.
  5. Considered and explicitly rejected: the NIWA/BRANZ M1/M2/M3 future weather files
     (Weather data/island_hourly_full_M{1,2,3}.csv). Checked directly: GHI/DNI/DHI and wind_speed
     are BIT-FOR-BIT IDENTICAL across M1/M2/M3 for both islands (standard CIBSE-style morphing
     only shifts temp_air/temp_dew/relative_humidity, +1.10 degC NI mean M1->M3; it does not
     re-simulate future irradiance or wind). These files therefore carry NO shape/timing signal
     and are not used here - using them as "three future shape chunks" would misrepresent what
     the dataset contains. (A temperature-derating effect on PV output is a real, separate,
     smaller amplitude-only lever - not built here, out of scope for this brief.)

METHOD: re-derives the renewables/residual/thermal-shape chain (build_edgs_dispatch.py Steps
A-B) in parallel, central (2021) template only, changing ONLY the solar shape lookup - every
other formula (demand shape, other renewables, DSR peak-shave, residual, thermal-shape cap,
MBIE-anchored thermal fuel CO2) is reproduced byte-for-byte from the shipped script. Verified
against the shipped baseline before trusting the adjusted run (see Step 0 sanity check below).

IMPORTANT CAUGHT-BEFORE-REPORTING ISSUE: reshaping WHEN solar is dispatched cannot change the
ANNUAL total. build_edgs_dispatch.py always normalises thermal_shape to sum=1 and applies MBIE's
own annual GWh per fuel, so total thermal generation/CO2 for the year is invariant to the solar
shape; solar's own annual GWh (and NI/SI split) is likewise unchanged. So total NI generation and
total NI CO2 for the year are IDENTICAL between baseline and real-shape runs, and the properly
energy-weighted annual EF (total CO2 / total generation - the published-style figure) is
UNCHANGED (verified below, ~0.00% by construction). An early draft of this script instead
reported the unweighted MEAN of the 8,760 hourly EF values, which moved by up to +23% - that
number is a real but different (and easily misread) statistic: concentrating solar into fewer,
sunnier hours creates many very-low-EF daytime hours and correspondingly higher-EF night hours
(no solar cushion at night at all, vs a constant small cushion under the flat fallback), which
shifts the unweighted average even though the true annual total does not move. Both figures are
reported below, clearly separated, to avoid this trap.

Outputs (output/edgs/):
  edgs_solar_shape_sensitivity_summary.csv   per scenario-year: energy-weighted annual EF
                                              (baseline vs real-shape, expected ~unchanged),
                                              unweighted hourly mean (distributional only),
                                              p99/max dirty-hour ceiling, and worst-hour timing
"""
import numpy as np
import pandas as pd

from edgs_common import (RESULTS_XLSX, ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, COMMODITY,
                         RENEWABLE_COMMODITIES, THERMAL_COMMODITIES,
                         MFE_FUEL_EF_KG_PER_GJ, WOOD_NONBIOGENIC_KG_PER_GJ, log_factory)

log, lines = log_factory()
CENTRAL_TEMPLATE = 2021
COMMODITY_TO_STD = {com: std for com, (std, _) in COMMODITY.items()}

# ---------------------------------------------------------------------------
# Load prerequisites (identical sources to build_edgs_dispatch.py)
# ---------------------------------------------------------------------------
targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
register = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")
merit = pd.read_parquet(OUT_DIR / "edgs_merit_order.parquet")
ren_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_renewables.parquet")
ren_shape = ren_shape_all[ren_shape_all["template_year"] == CENTRAL_TEMPLATE]
dem_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
dem_shape = dem_shape_all[dem_shape_all["template_year"] == CENTRAL_TEMPLATE]

# The real 2024 NI solar shape (confirmed non-flat, 8,784 rows)
real_solar_ni = ren_shape_all[(ren_shape_all["template_year"] == 2024)
                              & (ren_shape_all["island"] == "NI")
                              & (ren_shape_all["fuel_std"] == "SOL")]
assert len(real_solar_ni) > 0 and real_solar_ni["weight"].nunique() > 24, \
    "Expected a real (non-flat) 2024 NI solar shape - check edgs_shape_renewables.parquet"
log(f"Real 2024 NI solar shape: {len(real_solar_ni)} rows, "
    f"{real_solar_ni['weight'].nunique()} distinct weights (non-flat, confirmed)")

isd = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Island share of demand")
isd = isd[isd["Variable"] == "North Island share of national demand"]
ni_share_map = isd.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()

gem = pd.read_parquet(OUT_DIR / "edgs_gem_build.parquet")
gem_dsr = gem[gem["commodity"] == "Demand side response"]
dsr_cap_map = {}
for scen in SCENARIOS:
    s = gem_dsr[gem_dsr["scenario"] == scen]
    for yr in YEARS:
        dsr_cap_map[(scen, yr)] = float(s[s["year"] <= yr]["capacity_mw"].sum())

_use = pd.read_excel(RESULTS_XLSX, sheet_name="Electricity generation")
_use = _use[_use["Variable"] == "Electricity generation use"]
fuel_use_pj = _use.set_index(["Scenario", "TimePeriod", "Commodity"])["Value"].to_dict()
MFE_EF = {k: v[0] for k, v in MFE_FUEL_EF_KG_PER_GJ.items()}


def combustion_co2_kg(scenario, year, commodity):
    pj = fuel_use_pj.get((scenario, year, commodity), 0.0)
    ef = MFE_EF.get(commodity)
    return (pj * 1e6 * ef) if (ef is not None and pj) else 0.0


def wood_nonco2_kg(scenario, year):
    pj = fuel_use_pj.get((scenario, year, "Wood"), 0.0)
    return pj * 1e6 * WOOD_NONBIOGENIC_KG_PER_GJ if pj else 0.0


# ---------------------------------------------------------------------------
# Helpers (byte-for-byte reproductions of build_edgs_dispatch.py's own helpers)
# ---------------------------------------------------------------------------
def year_calendar(year):
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return pd.DataFrame({"datetime_hour": idx, "month": idx.month, "day": idx.day, "hour": idx.hour})


def map_weights(cal, wtab):
    m = cal.merge(wtab, on=["month", "day", "hour"], how="left")
    w = m["weight"].fillna(0.0).to_numpy()
    s = w.sum()
    return w / s if s > 0 else w


def peak_calibrate(shape_w, energy_mwh, peak_mw):
    raw = shape_w * energy_mwh
    mean, mx = raw.mean(), raw.max()
    if peak_mw <= mean or mx <= mean:
        return raw, mx
    k = (peak_mw - mean) / (mx - mean)
    out = mean + (raw - mean) * k
    return out, out.max()


def island_capacity_share(scenario):
    r = register[register["scenario"] == scenario]
    cap = r.groupby(["year", "commodity", "island"])["capacity_mw"].sum().reset_index()
    tot = cap.groupby(["year", "commodity"])["capacity_mw"].transform("sum")
    cap["share"] = np.where(tot > 0, cap["capacity_mw"] / tot, np.nan)
    return cap.set_index(["year", "commodity", "island"])["share"].to_dict()


# ---------------------------------------------------------------------------
# Core dispatch reconstruction, run TWICE per scenario-year: baseline (flat solar,
# reproducing the shipped pipeline exactly) and adjusted (real 2024 NI solar shape).
# ---------------------------------------------------------------------------
def run(scenario, year, use_real_solar_shape):
    cal = year_calendar(year)
    H = len(cal)
    cap_share = island_capacity_share(scenario)
    reg_s = register[register["scenario"] == scenario]
    merit_s = merit[(merit["scenario"] == scenario) & (merit["year"] == year)].sort_values("merit_rank")

    t = targets[(targets["scenario"] == scenario) & (targets["year"] == year)]
    annual_gen = t[t["metric"] == "net_generation"].set_index("commodity")["value"]
    demand_twh = float(t[t["metric"] == "annual_demand"]["value"].iloc[0])
    peak_gw = float(t[t["metric"] == "annual_peak"]["value"].iloc[0])
    ni_share = float(ni_share_map.get((scenario, year), 0.61))

    island_ren_total = {"NI": np.zeros(H), "SI": np.zeros(H)}
    ren_hourly = {}
    for com in RENEWABLE_COMMODITIES:
        gwh = float(annual_gen.get(com, 0.0))
        if gwh <= 0:
            continue
        std = COMMODITY_TO_STD[com]
        raw = {isl: cap_share.get((year, com, isl), np.nan) for isl in ("NI", "SI")}
        valid = {isl: s for isl, s in raw.items() if np.isfinite(s) and s > 0}
        tot = sum(valid.values())
        shares = ({isl: s / tot for isl, s in valid.items()} if tot > 0 else {"NI": 1.0})
        for isl, share in shares.items():
            if std == "SOL" and use_real_solar_shape:
                # Brief T: real 2024 NI solar shape, applied to both islands (disclosed
                # limitation for SI - see docstring point 4)
                w = map_weights(cal, real_solar_ni[["month", "day", "hour", "weight"]])
            else:
                wtab = ren_shape[(ren_shape.island == isl) & (ren_shape.fuel_std == std)]
                if len(wtab) == 0 or wtab["weight"].sum() == 0:
                    wtab = ren_shape[(ren_shape.island == "NI") & (ren_shape.fuel_std == std)]
                if len(wtab) == 0:
                    w = np.full(H, 1.0 / H)
                else:
                    w = map_weights(cal, wtab[["month", "day", "hour", "weight"]])
            mwh = gwh * 1000.0 * share * w
            ren_hourly[(isl, com)] = mwh
            island_ren_total[isl] += mwh

    w_ni = map_weights(cal, dem_shape[dem_shape.island == "NI"][["month", "day", "hour", "weight"]])
    w_si = map_weights(cal, dem_shape[dem_shape.island == "SI"][["month", "day", "hour", "weight"]])
    demand_mwh = demand_twh * 1e6
    netgen_mwh = float(annual_gen.sum()) * 1000.0
    nat_demand_raw = demand_mwh * ni_share * w_ni + demand_mwh * (1 - ni_share) * w_si
    nat_shape = nat_demand_raw / nat_demand_raw.sum()
    nat_demand = nat_shape * netgen_mwh

    nat_ren = island_ren_total["NI"] + island_ren_total["SI"]
    residual_pre = np.clip(nat_demand - nat_ren, 0.0, None)
    dsr_mw = float(dsr_cap_map.get((scenario, year), 0.0))
    residual = residual_pre.copy()
    if dsr_mw > 0:
        ndays = H // 24
        base = residual[:ndays * 24].reshape(ndays, 24)
        hi = base.argmax(axis=1); lo = base.argmin(axis=1)
        rows_idx = np.arange(ndays)
        shift = np.minimum(dsr_mw, base[rows_idx, hi])
        base[rows_idx, hi] -= shift
        base[rows_idx, lo] += shift
    dsr_series = residual_pre - residual

    caps = merit_s["capacity_mw"].to_numpy()
    total_cap = caps.sum()
    thermal_shape_raw = np.clip(residual, 0.0, total_cap)
    if thermal_shape_raw.sum() <= 0:
        thermal_shape_raw = np.full(H, 1.0)
    thermal_shape = thermal_shape_raw / thermal_shape_raw.sum()

    fuel_hourly, fuel_co2 = {}, {}
    for com in THERMAL_COMMODITIES:
        gwh = float(annual_gen.get(com, 0.0))
        co2_yr = combustion_co2_kg(scenario, year, com)
        if gwh <= 0 and co2_yr <= 0:
            continue
        fuel_hourly[com] = gwh * 1000.0 * thermal_shape
        fuel_co2[com] = co2_yr * thermal_shape

    wood_co2_yr = wood_nonco2_kg(scenario, year)
    wood_nonco2_ni = np.zeros(H)
    if wood_co2_yr > 0:
        wood_gen_total = sum(mwh.sum() for (isl, com), mwh in ren_hourly.items() if com == "Wood" and isl == "NI")
        if wood_gen_total > 0:
            wood_nonco2_ni += wood_co2_yr * (ren_hourly[("NI", "Wood")] / wood_gen_total)

    ni_co2 = sum(fuel_co2.values()) + wood_nonco2_ni  # kg (geothermal not adopted, stays 0)
    ni_gen = island_ren_total["NI"] + sum(fuel_hourly.values()) + dsr_series
    with np.errstate(divide="ignore", invalid="ignore"):
        ef_ni = np.where(ni_gen > 0, ni_co2 / (ni_gen * 1000.0), 0.0)
    return cal["datetime_hour"].to_numpy(), ef_ni, ni_gen, ni_co2


# ---------------------------------------------------------------------------
# Step 0: sanity check the reconstruction (baseline mode) against the shipped parquet
# ---------------------------------------------------------------------------
ship_ef = pd.read_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet",
                           columns=["scenario", "island", "datetime_hour", "ef_basis",
                                    "emission_factor_kg_co2e_per_kwh"])
ship_ni = ship_ef[(ship_ef.island == "NI") & (ship_ef.ef_basis == "generation")]
check_scenario, check_year = "Reference", 2035
dt_chk, ef_chk, _, _ = run(check_scenario, check_year, use_real_solar_shape=False)
ship_chk = (ship_ni[(ship_ni.scenario == check_scenario)]
            .set_index("datetime_hour").loc[dt_chk, "emission_factor_kg_co2e_per_kwh"].to_numpy())
resid = np.abs(ef_chk - ship_chk).max()
log(f"Step 0 sanity check ({check_scenario} {check_year}, baseline mode vs shipped): "
    f"max |diff| = {resid:.2e}")
if resid > 1e-6:
    log("WARNING: reconstruction does not match shipped baseline - results below are unreliable")
del ship_ef, ship_ni

# ---------------------------------------------------------------------------
# Run baseline vs adjusted for all 135 scenario-years
# ---------------------------------------------------------------------------
rows = []
for scenario in SCENARIOS:
    for year in YEARS:
        dt, ef_base, gen_base, co2_base = run(scenario, year, use_real_solar_shape=False)
        _, ef_real, gen_real, co2_real = run(scenario, year, use_real_solar_shape=True)
        base_worst_idx = int(np.argmax(ef_base))
        real_worst_idx = int(np.argmax(ef_real))
        # Properly energy-weighted annual EF (total CO2 / total generation) - NOT the same
        # as an unweighted average of the hourly EF values (see docstring note below on why
        # that distinction matters here).
        ew_base = co2_base.sum() / (gen_base.sum() * 1000.0) if gen_base.sum() > 0 else np.nan
        ew_real = co2_real.sum() / (gen_real.sum() * 1000.0) if gen_real.sum() > 0 else np.nan
        rows.append({
            "scenario": scenario, "year": year,
            "annual_ef_energy_weighted_baseline": ew_base,
            "annual_ef_energy_weighted_real_shape": ew_real,
            "unweighted_hourly_mean_baseline": ef_base.mean(),
            "unweighted_hourly_mean_real_shape": ef_real.mean(),
            "baseline_p99": np.quantile(ef_base, 0.99), "real_shape_p99": np.quantile(ef_real, 0.99),
            "baseline_max": ef_base.max(), "real_shape_max": ef_real.max(),
            "baseline_worst_hour_utc": pd.Timestamp(dt[base_worst_idx]),
            "real_shape_worst_hour_utc": pd.Timestamp(dt[real_worst_idx]),
            "worst_hour_shifted": bool(dt[base_worst_idx] != dt[real_worst_idx]),
        })
    log(f"  {scenario}: {len(YEARS)} years done")

summ = pd.DataFrame(rows)
summ["annual_ef_delta_pct"] = np.where(
    summ.annual_ef_energy_weighted_baseline > 0,
    (summ.annual_ef_energy_weighted_real_shape / summ.annual_ef_energy_weighted_baseline - 1) * 100, np.nan)
summ["p99_delta_pct"] = np.where(summ.baseline_p99 > 0,
                                  (summ.real_shape_p99 / summ.baseline_p99 - 1) * 100, np.nan)
summ["max_delta_pct"] = np.where(summ.baseline_max > 0,
                                  (summ.real_shape_max / summ.baseline_max - 1) * 100, np.nan)
summ.to_csv(OUT_DIR / "edgs_solar_shape_sensitivity_summary.csv", index=False)
log(f"\nWrote edgs_solar_shape_sensitivity_summary.csv ({len(summ):,} scenario-year rows)")

log(f"\nAnnual energy-weighted EF (published-style figure): max |delta| across all "
    f"{len(summ)} scenario-years = {summ.annual_ef_delta_pct.abs().max():.2e}% "
    f"(EXPECTED ~0 - MBIE's annual solar GWh, and therefore total annual generation and total "
    f"CO2, are conserved regardless of WHEN within the year solar is dispatched; this is a "
    f"consistency check, not a finding)")

n_shifted = int(summ.worst_hour_shifted.sum())
log(f"\nWorst-hour TIMING shifted in {n_shifted}/{len(summ)} scenario-years "
    f"(a genuine shape effect Brief S's uniform annual scaling could not produce)")

log("\nDirty-hour ceiling (p99 NI generation EF), baseline -> real-solar-shape, selected years:")
for scenario in SCENARIOS:
    s = summ[summ.scenario == scenario].set_index("year")
    parts = []
    for yr in (2024, 2030, 2040, 2050):
        if yr in s.index:
            r = s.loc[yr]
            parts.append(f"{yr}: {r.baseline_p99:.4f}->{r.real_shape_p99:.4f} ({r.p99_delta_pct:+.2f}%)")
    log(f"  {scenario}: " + " | ".join(parts))

(OUT_DIR / "processing_log_solar_shape_sensitivity.txt").write_text("\n".join(lines), encoding="utf-8")
log("\nNOT adopted into the shipped pipeline - standalone sensitivity only (see docstring).")
