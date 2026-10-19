"""
Test the HVDC capacity violation finding against wet/dry hydrology, not just the central
2021 template. This is the Assumption-1 sensitivity test for the HVDC finding, applied to
all 5 scenarios.

"median" (2017, the true median of the full 11-year 2015-2025 record; 2021 is the
3rd-driest, 18th percentile) is a 4th template, generated the same way as wet/dry below
(EDGS_TEMPLATE_YEAR=2017, all 5 scenarios -> edgs_hourly_generation_tmpl2017.parquet). It
shows whether choosing 2021 as "central" matters for the HVDC-violation figures, without
changing any result built on the 2021 template.

Method: the same transfer arithmetic as build_edgs_island_consumption.py and the other HVDC
reconstructions (island generation-level load renormalised to actual national generation;
required_transfer = genload - generation), unmodified and not recalibrated. Only the input
changes: which template's demand/renewable shape and which template's dispatched generation
are read, for each of central (2021), median (2017), wet (2023) and dry (2024). Wet/dry
generation for all 5 scenarios comes from plain re-runs of the unmodified
build_edgs_dispatch.py with EDGS_TEMPLATE_YEAR=2023/2024 (no scenario arg = all 5 scenarios),
writing edgs_hourly_generation_tmpl2023.parquet / _tmpl2024.parquet (separate files; the
central-template output is not touched).

The primary measure is the continuous violation magnitude (MW-hours over 1200 MW, integrated
per scenario-year), not the binary flag count, because the flag count is noise-sensitive at
this margin.

Outputs: edgs_hydro_sensitivity_summary.csv (15 scenario x template rows),
         edgs_hydro_sensitivity_mechanism.csv (SI export/demand/surplus breakdown)
"""
import numpy as np
import pandas as pd

from edgs_common import ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, COMMODITY, log_factory

log, lines = log_factory()
HVDC_CAPACITY_MW = 1200.0
TEMPLATES = {"central": (2021, ""), "median": (2017, "_tmpl2017"),
             "wet": (2023, "_tmpl2023"), "dry": (2024, "_tmpl2024")}

targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
dem_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
ren_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_renewables.parquet")
register = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")
merit = pd.read_parquet(OUT_DIR / "edgs_merit_order.parquet")

isd = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Island share of demand")
isd = isd[isd["Variable"] == "North Island share of national demand"]
ni_share_map = isd.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()

gem = pd.read_parquet(OUT_DIR / "edgs_gem_build.parquet")
dsr_gem = gem[gem.commodity == "Demand side response"]
dsr_cap_map = {}
for sc in SCENARIOS:
    s = dsr_gem[dsr_gem.scenario == sc]
    for yr in YEARS:
        dsr_cap_map[(sc, yr)] = float(s[s.year <= yr]["capacity_mw"].sum())

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


results = []
mechanism_rows = []

for tmpl_name, (tmpl_year, suffix) in TEMPLATES.items():
    log(f"\n=== Template: {tmpl_name} ({tmpl_year}) ===")
    dem_shape = dem_shape_all[dem_shape_all.template_year == tmpl_year]
    ren_shape = ren_shape_all[ren_shape_all.template_year == tmpl_year]
    # Solar real-shape fallback, same as build_edgs_dispatch.py
    REAL_SOLAR_SHAPE = ren_shape_all[(ren_shape_all.template_year == 2024)
                                     & (ren_shape_all.island == "NI") & (ren_shape_all.fuel_std == "SOL")]
    gen = pd.read_parquet(OUT_DIR / f"edgs_hourly_generation{suffix}.parquet")
    gen["year"] = pd.to_datetime(gen["datetime_hour"]).dt.year

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

            # renewables, island totals, THIS template's shape
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
            nat_demand = nat_shape * netgen_mwh
            residual_pre = np.clip(nat_demand - nat_ren, 0.0, None)

            dsr_mw = dsr_cap_map[(scenario, year)]
            residual, dsr_series = peak_shave(residual_pre, dsr_mw, H)

            mplants = merit[(merit.scenario == scenario) & (merit.year == year)].sort_values("merit_rank")
            total_cap = mplants["capacity_mw"].sum()
            th_shape_raw = np.clip(residual, 0.0, total_cap)
            th_shape = th_shape_raw / th_shape_raw.sum() if th_shape_raw.sum() > 0 else np.full(H, 1.0 / H)
            thermal_total_mwh = sum(float(annual_gen.get(c, 0.0)) for c in
                                    ("Coal", "Natural gas", "Diesel", "LPG", "Fuel oil")) * 1000.0

            g_NI = island_ren_total["NI"] + thermal_total_mwh * th_shape + dsr_series
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
            transfer_to_NI = gl_NI - g_NI

            max_mw = float(np.abs(transfer_to_NI).max())
            n_hours = int((np.abs(transfer_to_NI) > HVDC_CAPACITY_MW).sum())
            continuous_mag = float(np.clip(np.abs(transfer_to_NI) - HVDC_CAPACITY_MW, 0, None).sum())

            results.append({"template": tmpl_name, "template_year": tmpl_year, "scenario": scenario,
                            "year": year, "max_transfer_mw": max_mw, "n_hours_violate": n_hours,
                            "continuous_mag_MWh": continuous_mag})

            # Mechanism data (Step 3 table): SI hydro generation (annual GWh), SI island demand
            # target (annual, from island_demand share x shape), SI exportable surplus
            si_hydro_gwh = float(annual_gen.get("Hydro", 0.0)) * cap_share.get((year, "Hydro", "SI"), 0.0) \
                if np.isfinite(cap_share.get((year, "Hydro", "SI"), np.nan)) else 0.0
            si_gen_total_mwh = g_SI.sum()
            si_genload_mwh = nat_gen.sum() - gl_NI.sum()  # SI's share of national genload target
            si_surplus_mwh = si_gen_total_mwh - si_genload_mwh  # positive = net exportable
            mechanism_rows.append({"template": tmpl_name, "scenario": scenario, "year": year,
                                   "si_hydro_annual_gwh": si_hydro_gwh,
                                   "si_generation_total_mwh": si_gen_total_mwh,
                                   "si_genload_target_mwh": si_genload_mwh,
                                   "si_net_surplus_mwh": si_surplus_mwh})
    log(f"  {tmpl_name}: all 5 scenarios done")

res_df = pd.DataFrame(results)
res_df.to_csv(OUT_DIR / "edgs_hydro_sensitivity_summary.csv", index=False)
mech_df = pd.DataFrame(mechanism_rows)
mech_df.to_csv(OUT_DIR / "edgs_hydro_sensitivity_mechanism.csv", index=False)

# Summary table, scenario x template
log("\n=== Step 2: violation count & continuous magnitude, scenario x template ===")
summ = res_df.groupby(["scenario", "template"]).apply(
    lambda x: pd.Series({"n_flagged_sy": int((x.max_transfer_mw > HVDC_CAPACITY_MW).sum()),
                         "total_continuous_MWh": x.continuous_mag_MWh.sum()}),
    include_groups=False).unstack("template")
log(summ.to_string())

tot = res_df.groupby("template").apply(
    lambda x: pd.Series({"n_flagged_sy": int((x.max_transfer_mw > HVDC_CAPACITY_MW).sum()),
                         "total_continuous_MWh": x.continuous_mag_MWh.sum()}),
    include_groups=False)
log("\n=== Total (all 5 scenarios, 27 years = 135 scenario-years, per template) ===")
log(tot.to_string())

# Mechanism - SI surplus decomposition, central vs wet vs dry
log("\n=== Step 3: SI hydro / generation / genload-target / surplus, by template (all scenarios, annual sums TWh) ===")
mech_summ = mech_df.groupby("template")[["si_hydro_annual_gwh", "si_generation_total_mwh",
                                         "si_genload_target_mwh", "si_net_surplus_mwh"]].sum()
mech_summ["si_hydro_annual_gwh"] = mech_summ["si_hydro_annual_gwh"]
mech_summ[["si_generation_total_mwh", "si_genload_target_mwh", "si_net_surplus_mwh"]] /= 1e6  # -> TWh
mech_summ.columns = ["si_hydro_GWh_sum", "si_generation_TWh", "si_genload_target_TWh", "si_net_surplus_TWh"]
log(mech_summ.round(2).to_string())

(OUT_DIR / "processing_log_hydro_sensitivity.txt").write_text("\n".join(lines), encoding="utf-8")
log("\nWrote edgs_hydro_sensitivity_summary.csv, edgs_hydro_sensitivity_mechanism.csv")
