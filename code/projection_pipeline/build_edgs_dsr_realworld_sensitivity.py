"""
DSR timing sensitivity: test Assumption 2's model-original DSR/battery peak-shave rule (charge
at the day's lowest residual hour, discharge at the day's highest) against a real-world-cited
alternative: AEMO's published evening-peak battery discharge window for Australia's NEM.
Standalone: reads only existing pipeline parquets, writes only new CSVs. Does not modify
build_edgs_dispatch.py, edgs_common.py, or any pipeline output parquet.

Background: Assumption 2 (edgs_common.py) is labelled "model-original, NOT MBIE-derived".
MBIE gives only DSR capacity (MW) by scenario-year, never a dispatch rule. The question is
whether a real market's observed battery behaviour can ground the rule instead of an invented
one. Australia's NEM (comparable regulatory heritage to NZ's market; grid-scale, not
household-only) publishes this kind of timing data quarterly.

External source: AEMO, "Quarterly Energy Dynamics - Q1 2026"
(https://www.aemo.com.au/-/media/files/major-publications/qed/2026/qed-q1-2026.pdf):
  - Section 2.4.1 "Batteries" (grid-scale BESS, the comparable case to NZ's DSR/BESS):
    record discharge 3,556 MW at the half-hour ending 1900 hrs (7pm), 7 Jan 2026; record
    charging 2,742 MW, concentrated in daytime hours associated with solar surplus. AEMO's own
    Figure 56 tracks "change in average battery discharge/charge by time of day".
  - Household/CER section (p.11): evening peak window stated as "1600 hrs to 2100 hrs";
    charging described as "daytime... mid-morning", tied to rooftop solar + grid supply.

Design (this script's own reading of the citation, disclosed as such):
  - Discharge window: 1600-2100 hrs (16,17,18,19,20), AEMO's own stated evening-peak
    window, verbatim from the source.
  - Charge window: 0900-1500 hrs (9,10,11,12,13,14), this script's own interpretation of
    AEMO's qualitative "daytime... mid-morning" charging description, since AEMO gives no
    precise charge-window hours the way it does for the evening-peak discharge window. This is
    a reasoned reading, not a direct citation (same standard as the 2032 HVDC capacity
    cutover year in build_edgs_hvdc_capacity_correction.py).
  - Energy, not shape, is held constant: each day's total discharge/charge energy is kept
    identical to what the pipeline's residual-driven rule moves that day (so this is a pure
    timing test, not a magnitude/capacity test), spread uniformly across the cited window
    (the least-assumption choice within the window, since AEMO gives no finer sub-window shape
    for either case).

Method: re-derives the load/residual/thermal-shape/EF chain of build_edgs_dispatch.py in
parallel, central (2021) template, real-solar-shape baseline, changing only the DSR peak-shave
rule; every other formula is reproduced from the pipeline script. Sanity-checked before
trusting the result (baseline-mode reconstruction must reproduce the pipeline EF exactly).

Outputs (output/edgs/):
  edgs_dsr_realworld_match.csv        per scenario-year-day: does the pipeline's own chosen
                                       discharge hour already fall inside AEMO's cited
                                       1600-2100hrs window? (quantifies how close in shape
                                       the two rules already are)
  edgs_dsr_realworld_sensitivity_summary.csv   per scenario-year: pipeline vs AEMO-window NI
                                       generation EF (mean/p99/max) and HVDC-relevant residual
                                       peak timing
"""
import numpy as np
import pandas as pd

from edgs_common import (RESULTS_XLSX, ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, COMMODITY,
                         RENEWABLE_COMMODITIES, THERMAL_COMMODITIES,
                         MFE_FUEL_EF_KG_PER_GJ, WOOD_NONBIOGENIC_KG_PER_GJ, log_factory)

log, lines = log_factory()
CENTRAL_TEMPLATE = 2021
COMMODITY_TO_STD = {com: std for com, (std, _) in COMMODITY.items()}
AEMO_DISCHARGE_HOURS = [16, 17, 18, 19, 20]   # 1600-2100 hrs, AEMO's own stated window
AEMO_CHARGE_HOURS = [9, 10, 11, 12, 13, 14]   # 0900-1500 hrs, this script's reading of "daytime/mid-morning"
AEMO_SOURCE = ("AEMO, 'Quarterly Energy Dynamics - Q1 2026' "
               "(aemo.com.au/-/media/files/major-publications/qed/2026/qed-q1-2026.pdf), "
               "Section 2.4.1 Batteries + household/CER section p.11")
log(f"Source: {AEMO_SOURCE}")
log(f"Discharge window (AEMO-stated): hrs {AEMO_DISCHARGE_HOURS}; "
    f"charge window (this script's reading): hrs {AEMO_CHARGE_HOURS}")

# Load prerequisites (identical sources to build_edgs_dispatch.py)
targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
register = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")
merit = pd.read_parquet(OUT_DIR / "edgs_merit_order.parquet")
ren_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_renewables.parquet")
ren_shape = ren_shape_all[ren_shape_all["template_year"] == CENTRAL_TEMPLATE]
dem_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
dem_shape = dem_shape_all[dem_shape_all["template_year"] == CENTRAL_TEMPLATE]
REAL_SOLAR_SHAPE = ren_shape_all[(ren_shape_all["template_year"] == 2024)
                                 & (ren_shape_all["island"] == "NI") & (ren_shape_all["fuel_std"] == "SOL")]

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


def year_calendar(year):
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return pd.DataFrame({"datetime_hour": idx, "month": idx.month, "day": idx.day, "hour": idx.hour})


def map_weights(cal, wtab):
    m = cal.merge(wtab, on=["month", "day", "hour"], how="left")
    w = m["weight"].fillna(0.0).to_numpy()
    s = w.sum()
    return w / s if s > 0 else w


def island_capacity_share(scenario):
    r = register[register["scenario"] == scenario]
    cap = r.groupby(["year", "commodity", "island"])["capacity_mw"].sum().reset_index()
    tot = cap.groupby(["year", "commodity"])["capacity_mw"].transform("sum")
    cap["share"] = np.where(tot > 0, cap["capacity_mw"] / tot, np.nan)
    return cap.set_index(["year", "commodity", "island"])["share"].to_dict()


def dsr_shipped(residual_pre, dsr_mw, H):
    """Pipeline rule: discharge at the day's max residual hour, charge at the day's min."""
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


def dsr_aemo(residual_pre, dsr_mw, H):
    """AEMO-cited rule: same daily energy as the pipeline rule would move, but spread uniformly
    across AEMO's stated discharge window (1600-2100hrs) and this script's reading of the
    charge window (0900-1500hrs), instead of concentrated in a single residual-driven hour."""
    residual = residual_pre.copy()
    dsr_series = np.zeros(H)
    if dsr_mw > 0:
        ndays = H // 24
        base = residual_pre[:ndays * 24].reshape(ndays, 24)
        hi = base.argmax(axis=1)
        rows_idx = np.arange(ndays)
        daily_energy = np.minimum(dsr_mw, base[rows_idx, hi])  # same magnitude rule as pipeline
        disch_per_hr = daily_energy / len(AEMO_DISCHARGE_HOURS)
        chg_per_hr = daily_energy / len(AEMO_CHARGE_HOURS)
        out = residual_pre[:ndays * 24].reshape(ndays, 24).copy()
        for h in AEMO_DISCHARGE_HOURS:
            out[:, h] -= disch_per_hr
        for h in AEMO_CHARGE_HOURS:
            out[:, h] += chg_per_hr
        residual = np.concatenate([out.reshape(-1), residual_pre[ndays * 24:]])
        residual = np.clip(residual, 0.0, None)
        dsr_series = residual_pre - residual
    return residual, dsr_series


def run(scenario, year, mode):
    """mode: 'shipped' (pipeline rule) or 'aemo'"""
    cal = year_calendar(year)
    H = len(cal)
    cap_share = island_capacity_share(scenario)
    merit_s = merit[(merit["scenario"] == scenario) & (merit["year"] == year)].sort_values("merit_rank")

    t = targets[(targets["scenario"] == scenario) & (targets["year"] == year)]
    annual_gen = t[t["metric"] == "net_generation"].set_index("commodity")["value"]
    demand_twh = float(t[t["metric"] == "annual_demand"]["value"].iloc[0])
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
            if std == "SOL":
                w = map_weights(cal, REAL_SOLAR_SHAPE[["month", "day", "hour", "weight"]])
            else:
                wtab = ren_shape[(ren_shape.island == isl) & (ren_shape.fuel_std == std)]
                if len(wtab) == 0 or wtab["weight"].sum() == 0:
                    wtab = ren_shape[(ren_shape.island == "NI") & (ren_shape.fuel_std == std)]
                w = map_weights(cal, wtab[["month", "day", "hour", "weight"]]) if len(wtab) else np.full(H, 1.0 / H)
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
    if mode == "shipped":
        residual, dsr_series = dsr_shipped(residual_pre, dsr_mw, H)
    else:
        residual, dsr_series = dsr_aemo(residual_pre, dsr_mw, H)

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

    ni_co2 = sum(fuel_co2.values()) + wood_nonco2_ni
    ni_gen = island_ren_total["NI"] + sum(fuel_hourly.values()) + dsr_series
    with np.errstate(divide="ignore", invalid="ignore"):
        ef_ni = np.where(ni_gen > 0, ni_co2 / (ni_gen * 1000.0), 0.0)
    return cal["datetime_hour"].to_numpy(), ef_ni, ni_gen, ni_co2, dsr_series, residual_pre


# Sanity check (pipeline-rule mode must reproduce the pipeline's EF parquet exactly)
ship_ef = pd.read_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet",
                           columns=["scenario", "island", "datetime_hour", "ef_basis",
                                    "emission_factor_kg_co2e_per_kwh"])
ship_ni = ship_ef[(ship_ef.island == "NI") & (ship_ef.ef_basis == "generation")]
check_scenario, check_year = "Reference", 2040
dt_chk, ef_chk, *_ = run(check_scenario, check_year, "shipped")
ship_chk = (ship_ni[(ship_ni.scenario == check_scenario)]
            .set_index("datetime_hour").loc[dt_chk, "emission_factor_kg_co2e_per_kwh"].to_numpy())
resid = np.abs(ef_chk - ship_chk).max()
log(f"Step 0 sanity check ({check_scenario} {check_year}, shipped mode vs shipped baseline): "
    f"max |diff| = {resid:.2e}")
if resid > 1e-6:
    log("WARNING: reconstruction does not match shipped baseline - results below are unreliable")
del ship_ef, ship_ni

# Part 1: match rate - how often does the pipeline's own chosen discharge hour
# already fall inside AEMO's cited 1600-2100hrs window?
match_rows = []
for scenario in SCENARIOS:
    for year in YEARS:
        cal = year_calendar(year)
        H = len(cal)
        _, _, _, _, dsr_series, residual_pre = run(scenario, year, "shipped")
        dsr_mw = float(dsr_cap_map.get((scenario, year), 0.0))
        if dsr_mw <= 0:
            continue
        ndays = H // 24
        base = residual_pre[:ndays * 24].reshape(ndays, 24)
        hi = base.argmax(axis=1)
        in_window = np.isin(hi, AEMO_DISCHARGE_HOURS)
        match_rows.append({"scenario": scenario, "year": year, "n_days": ndays,
                           "n_days_in_aemo_window": int(in_window.sum()),
                           "pct_days_in_aemo_window": float(in_window.mean() * 100)})
    log(f"  {scenario}: match-rate computed")
match_df = pd.DataFrame(match_rows)
match_df.to_csv(OUT_DIR / "edgs_dsr_realworld_match.csv", index=False)
overall_match = (match_df.n_days_in_aemo_window.sum() / match_df.n_days.sum() * 100) if len(match_df) else float("nan")
log(f"\nOverall: shipped model's own discharge hour falls inside AEMO's 1600-2100hrs window "
    f"on {overall_match:.1f}% of days ({match_df.n_days_in_aemo_window.sum():,} of "
    f"{match_df.n_days.sum():,} DSR-active scenario-year-days)")

# Part 2: full sensitivity - pipeline rule vs AEMO-window rule, same energy, different timing
rows = []
for scenario in SCENARIOS:
    for year in YEARS:
        dt, ef_ship, gen_ship, co2_ship, *_ = run(scenario, year, "shipped")
        _, ef_aemo, gen_aemo, co2_aemo, *_ = run(scenario, year, "aemo")
        ew_ship = co2_ship.sum() / (gen_ship.sum() * 1000.0) if gen_ship.sum() > 0 else np.nan
        ew_aemo = co2_aemo.sum() / (gen_aemo.sum() * 1000.0) if gen_aemo.sum() > 0 else np.nan
        rows.append({
            "scenario": scenario, "year": year,
            "annual_ef_energy_weighted_shipped": ew_ship,
            "annual_ef_energy_weighted_aemo": ew_aemo,
            "shipped_p99": np.quantile(ef_ship, 0.99), "aemo_p99": np.quantile(ef_aemo, 0.99),
            "shipped_max": ef_ship.max(), "aemo_max": ef_aemo.max(),
        })
    log(f"  {scenario}: full sensitivity done")

summ = pd.DataFrame(rows)
summ["annual_ef_delta_pct"] = np.where(summ.annual_ef_energy_weighted_shipped > 0,
    (summ.annual_ef_energy_weighted_aemo / summ.annual_ef_energy_weighted_shipped - 1) * 100, np.nan)
summ["p99_delta_pct"] = np.where(summ.shipped_p99 > 0,
    (summ.aemo_p99 / summ.shipped_p99 - 1) * 100, np.nan)
summ["max_delta_pct"] = np.where(summ.shipped_max > 0,
    (summ.aemo_max / summ.shipped_max - 1) * 100, np.nan)
summ.to_csv(OUT_DIR / "edgs_dsr_realworld_sensitivity_summary.csv", index=False)
log(f"\nWrote edgs_dsr_realworld_sensitivity_summary.csv ({len(summ):,} scenario-year rows)")

log(f"\nAnnual energy-weighted EF: max |delta| = {summ.annual_ef_delta_pct.abs().max():.2e}% "
    f"(EXPECTED ~0 - same daily energy shifted either way, only timing differs)")

log("\nDirty-hour ceiling (p99 NI generation EF), shipped -> AEMO-window, selected years:")
for scenario in SCENARIOS:
    s = summ[summ.scenario == scenario].set_index("year")
    parts = []
    for yr in (2024, 2030, 2040, 2050):
        if yr in s.index:
            r = s.loc[yr]
            parts.append(f"{yr}: {r.shipped_p99:.4f}->{r.aemo_p99:.4f} ({r.p99_delta_pct:+.2f}%)")
    log(f"  {scenario}: " + " | ".join(parts))

(OUT_DIR / "processing_log_dsr_realworld_sensitivity.txt").write_text("\n".join(lines), encoding="utf-8")
log("\nNOT adopted into the shipped pipeline - standalone sensitivity only (see docstring).")
