"""
Module 5: hourly, island-resolved generation and emission factor
for one or more scenarios, reconciled to MBIE annual national totals.

Method:
  Renewables  : MBIE annual net generation (GWh) per fuel  [MBIE_annual_disaggregated]
                x island capacity share (Generation Stack register, per year)
                x historical hourly weight (Assumption 1, central template).
  Demand      : MBIE annual demand (TWh) split NI/SI by MBIE 'Island share of demand',
                shaped by historical hourly demand weight, then peak-calibrated
                (energy-preserving) so national hourly max == MBIE annual peak (GW).
  Thermal     : the residual load (demand left after renewables and storage shifting), capped
                at the year's total thermal capacity from the merit-order table (Module 3),
                sets one thermal hourly shape. Every thermal fuel follows that same shape;
                MBIE's published annual fuel GWh set the fuel split. Rationale: MBIE publishes no hourly fuel split, and a pure
                marginal-cost ordering does not reproduce NZ's gas-supply-constrained coal
                dispatch (coal is dearer than gas, yet MBIE still runs about 1 TWh of coal).
                Imposing a gas-supply cap to force that would add a third assumption,
                which the method excludes. Each thermal fuel is therefore MBIE annual GWh x
                the normalised thermal shape, so the annual total reconciles exactly per
                fuel by construction. CO2 per fuel =
                MBIE published fuel input (Electricity generation use, Gross PJ) x MfE factor
                (combustion_co2_kg below), not plant heat rates. The merit-order ranking
                itself does not enter the hourly results.
                All thermal capacity is North Island (Module 2), so all thermal is assigned to NI.
  Geothermal  : fugitive CO2-e is not included (geo_co2_by_island is zero; see the
                geothermal block in the body). The projection is combustion scope only, so
                it is not like-for-like with the metered series, which counts geothermal
                fugitive CO2. Tests on record: (1) a McLean & Richardson (2019) capacity-
                weighted fleet factor on all geothermal (Ngawha 0 g/kWh from 2024) overshot
                MBIE's electricity GHG total by about 19-27% (emissions-weighted), worse than
                combustion only (about 6.3%); (2) build_edgs_check2_geothermal_resolution.py
                found that about 81 g/kWh applied only to geothermal built above the 2024
                fleet reproduces MBIE's total to about 1.8%. That factor is not applied here.
                geothermal_ef_kg_per_mwh (edgs_common.py) is kept for the diagnostics.
  Wood        : non-biogenic CH4+N2O only (MBIE Wood fuel input x MfE Table 3.4); wood CO2 is
                biogenic and zero-rated.
  Battery/DSR : Assumption 2 (model-original). DSR discharges to shave the highest-residual
                hours, total energy capped at MBIE annual DSR GWh. Labelled assumption_2.
  Emission factor (per island, per hour) = island (thermal combustion + wood non-CO2) CO2-e
                (kg) / island total generation (kWh). Generation-side basis.

Usage: python build_edgs_dispatch.py [Scenario ...]   (default: all five)
"""
import os
import sys
import numpy as np
import pandas as pd

from edgs_common import (island_capacity_share, map_weights, peak_calibrate, RESULTS_XLSX, ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, COMMODITY,
                         RENEWABLE_COMMODITIES, THERMAL_COMMODITIES,
                         MFE_FUEL_EF_KG_PER_GJ, geothermal_ef_kg_per_mwh,
                         WOOD_NONBIOGENIC_KG_PER_GJ,
                         log_factory)

log, lines = log_factory()
run_scenarios = [s for s in sys.argv[1:] if s in SCENARIOS] or SCENARIOS
# Assumption-1 template year: central 2021 (median hydro); wet 2023 / dry 2024 for the
# sensitivity case (Module 6 sets EDGS_TEMPLATE_YEAR). Non-central runs get a file suffix.
CENTRAL_TEMPLATE = int(os.environ.get("EDGS_TEMPLATE_YEAR", "2021"))

# Load prerequisites
targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
register = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")
merit = pd.read_parquet(OUT_DIR / "edgs_merit_order.parquet")
ren_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_renewables.parquet")
ren_shape = ren_shape_all[ren_shape_all["template_year"] == CENTRAL_TEMPLATE]
# Solar-specific real-shape fallback: EA/EMI carries no Solar fuel code before 2024, so the
# 2017/2021/2023 templates have no solar rows and would otherwise fall through to a flat 24h
# spread, which is physically wrong (solar generating at night). The observed 2024 NI solar
# shape (non-flat, 8,784 hourly weights) is used in its place whenever the chosen template
# lacks solar data, for both islands. No real SI solar shape exists in any template; this is
# a disclosed limitation. build_edgs_solar_shape_sensitivity.py confirms the fallback changes
# only the hourly timing of solar dispatch, never the annual total (MBIE's GWh is unchanged),
# so Checks 1-3 are unaffected.
REAL_SOLAR_SHAPE = ren_shape_all[(ren_shape_all["template_year"] == 2024)
                                 & (ren_shape_all["island"] == "NI")
                                 & (ren_shape_all["fuel_std"] == "SOL")]
# Regression-testing knob only (not a documented pipeline option): set
# EDGS_DISABLE_SOLAR_FIX=1 to reproduce the flat-solar baseline for a like-for-like
# comparison with the solar fallback. Default off.
DISABLE_SOLAR_FIX = os.environ.get("EDGS_DISABLE_SOLAR_FIX", "0") == "1"
dem_shape = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
dem_shape = dem_shape[dem_shape["template_year"] == CENTRAL_TEMPLATE]

COMMODITY_TO_STD = {com: std for com, (std, _) in COMMODITY.items()}

# MBIE Island share of demand (NI fraction), by scenario x year
isd = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Island share of demand")
isd = isd[isd["Variable"] == "North Island share of national demand"]
ni_share_map = isd.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()

# DSR/battery capacity (Assumption 2 driver): cumulative GEM build-schedule DSR MW by
# scenario x year (national). MBIE carries DSR only as capacity, never net generation.
gem = pd.read_parquet(OUT_DIR / "edgs_gem_build.parquet")
gem_dsr = gem[gem["commodity"] == "Demand side response"]
dsr_cap_map = {}
for scen in SCENARIOS:
    s = gem_dsr[gem_dsr["scenario"] == scen]
    for yr in YEARS:
        dsr_cap_map[(scen, yr)] = float(s[s["year"] <= yr]["capacity_mw"].sum())

# MBIE published fuel input per commodity (Electricity generation use, Gross PJ).
# Combustion CO2 is computed directly from this x MfE factors, not from plant heat rates
# (heat-rate combustion undershoots MBIE by about 11%). Heat rate is kept only for the
# merit-order ranking in Module 3.
_use = pd.read_excel(RESULTS_XLSX, sheet_name="Electricity generation")
_use = _use[_use["Variable"] == "Electricity generation use"]  # Gross PJ
fuel_use_pj = _use.set_index(["Scenario", "TimePeriod", "Commodity"])["Value"].to_dict()
MFE_EF = {k: v[0] for k, v in MFE_FUEL_EF_KG_PER_GJ.items()}  # kg CO2-e / GJ


def combustion_co2_kg(scenario, year, commodity):
    """MBIE fuel input (Gross PJ) x MfE factor, in kg CO2-e, for one thermal commodity and year."""
    pj = fuel_use_pj.get((scenario, year, commodity), 0.0)
    ef = MFE_EF.get(commodity)
    return (pj * 1e6 * ef) if (ef is not None and pj) else 0.0  # PJ*1e6 GJ * kg/GJ


def wood_nonco2_kg(scenario, year):
    """MBIE Wood fuel input (Gross PJ, the same figure used for Wood generation/dispatch)
    x MfE Table 3.4 non-biogenic CH4+N2O factor, in kg CO2-e, for one scenario and year.
    Source: WOOD_NONBIOGENIC_SOURCE (edgs_common.py). CO2 from Wood remains biogenic/
    zero-rated, untouched; this is an additive non-CO2 term only."""
    pj = fuel_use_pj.get((scenario, year, "Wood"), 0.0)
    return pj * 1e6 * WOOD_NONBIOGENIC_KG_PER_GJ if pj else 0.0  # PJ*1e6 GJ * kg/GJ


# Geothermal fugitive CO2 factor (cited): capacity-weighted average across the
# actual commissioned geothermal fleet, per scenario-year, from the plant register.
# kg/MWh numerically equals the source's g CO2-e/kWh (units cancel: g/kWh = kg/MWh).
_geo_reg = register[register["commodity"] == "Geothermal"].copy()
_geo_reg["ef_kg_per_mwh"] = [geothermal_ef_kg_per_mwh(p, y)[0]
                             for p, y in zip(_geo_reg["plant"], _geo_reg["year"])]
geo_fleet_ef = {}
for (sc, yr), g in _geo_reg.groupby(["scenario", "year"]):
    geo_fleet_ef[(sc, yr)] = (float(np.average(g["ef_kg_per_mwh"], weights=g["capacity_mw"]))
                              if g["capacity_mw"].sum() > 0 else np.nan)


# Helpers
def year_calendar(year):
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return pd.DataFrame({"datetime_hour": idx, "month": idx.month, "day": idx.day, "hour": idx.hour})


# Dispatch
gen_rows, ef_rows, recon_log, peak_log = [], [], [], []

for scenario in run_scenarios:
    log(f"\n===== {scenario} =====")
    cap_share = island_capacity_share(register, scenario)
    reg_s = register[register["scenario"] == scenario]
    merit_s = merit[merit["scenario"] == scenario]

    for year in YEARS:
        cal = year_calendar(year)
        H = len(cal)
        dt = cal["datetime_hour"].to_numpy()
        t = targets[(targets["scenario"] == scenario) & (targets["year"] == year)]
        annual_gen = t[t["metric"] == "net_generation"].set_index("commodity")["value"]  # GWh
        demand_twh = float(t[t["metric"] == "annual_demand"]["value"].iloc[0])
        peak_gw = float(t[t["metric"] == "annual_peak"]["value"].iloc[0])
        ni_share = float(ni_share_map.get((scenario, year), 0.61))

        # Renewables (MBIE annual x island cap share x hourly weight)
        ren_hourly = {}          # keyed by (island, commodity): (mwh_array, fallback_note)
        island_ren_total = {"NI": np.zeros(H), "SI": np.zeros(H)}
        for com in RENEWABLE_COMMODITIES:
            gwh = float(annual_gen.get(com, 0.0))
            if gwh <= 0:
                continue
            std = COMMODITY_TO_STD[com]
            # normalised island shares (guaranteed to sum to 1 so every MBIE GWh is
            # allocated). Fall back to NI when the register has no capacity for this
            # commodity-year (e.g. Wood/Waste heat with generation but no stack plant).
            raw = {isl: cap_share.get((year, com, isl), np.nan) for isl in ("NI", "SI")}
            valid = {isl: s for isl, s in raw.items() if np.isfinite(s) and s > 0}
            tot = sum(valid.values())
            shares = ({isl: s / tot for isl, s in valid.items()} if tot > 0 else {"NI": 1.0})
            for isl, share in shares.items():
                wtab = ren_shape[(ren_shape.island == isl) & (ren_shape.fuel_std == std)]
                fb = ""
                if (len(wtab) == 0 or wtab["weight"].sum() == 0) and std == "SOL" and not DISABLE_SOLAR_FIX:
                    wtab = REAL_SOLAR_SHAPE
                    fb = " [A1 solar fallback: real 2024 NI shape, adopted]"
                elif len(wtab) == 0 or wtab["weight"].sum() == 0:
                    wtab = ren_shape[(ren_shape.island == "NI") & (ren_shape.fuel_std == std)]
                    fb = " [A1 fallback: NI shape]"
                if len(wtab) == 0:
                    w = np.full(H, 1.0 / H); fb = " [A1 fallback: flat baseload]"
                else:
                    w = map_weights(cal, wtab[["month", "day", "hour", "weight"]], template_year=(2024 if fb.startswith(" [A1 solar") else CENTRAL_TEMPLATE))
                mwh = gwh * 1000.0 * share * w
                ren_hourly[(isl, com)] = (mwh, fb)
                island_ren_total[isl] += mwh

        # Two load series with different annual totals:
        #  (i) demand series: energy = MBIE Total electricity demand, peak-calibrated to
        #      MBIE Peak demand. Used only for the Check-3 peak validation (demand-side).
        #  (ii) generation-level load series: energy = MBIE net generation total (demand +
        #      T&D losses + own use, about 7.2% higher). Used for the dispatch residual, because
        #      thermal serves generation-level load, not delivered demand. Same historical
        #      hourly shape (MBIE publishes no generation-level shape); only the annual
        #      total the shape is scaled to differs. Not peak-calibrated to the demand peak.
        w_ni = map_weights(cal, dem_shape[dem_shape.island == "NI"][["month", "day", "hour", "weight"]], template_year=CENTRAL_TEMPLATE)
        w_si = map_weights(cal, dem_shape[dem_shape.island == "SI"][["month", "day", "hour", "weight"]], template_year=CENTRAL_TEMPLATE)
        demand_mwh = demand_twh * 1e6
        netgen_mwh = float(annual_gen.sum()) * 1000.0  # MBIE net generation, all commodities
        nat_demand_raw = demand_mwh * ni_share * w_ni + demand_mwh * (1 - ni_share) * w_si
        nat_shape = nat_demand_raw / nat_demand_raw.sum()
        # (i) demand series for Check 3
        _demand_cal, achieved_peak = peak_calibrate(nat_shape, demand_mwh, peak_gw * 1e3)
        peak_log.append({"scenario": scenario, "year": year, "mbie_peak_gw": peak_gw,
                         "model_peak_gw": achieved_peak / 1e3})
        # (ii) generation-level load for the dispatch residual
        nat_demand = nat_shape * netgen_mwh

        # Assumption 2: DSR/battery daily peak-shave load-shift (capacity-driven)
        # MBIE carries DSR/battery only as capacity (never net generation), so this rule
        # is model-original. Each day the fleet discharges up to its rated MW in that day's
        # highest-residual hour and charges the same energy in the lowest-residual hour
        # (an energy-neutral daily cycle, so net annual generation is near 0, matching MBIE's 0).
        nat_ren = island_ren_total["NI"] + island_ren_total["SI"]
        residual_pre = np.clip(nat_demand - nat_ren, 0.0, None)
        dsr_mw = float(dsr_cap_map.get((scenario, year), 0.0))
        residual = residual_pre.copy()
        if dsr_mw > 0:
            ndays = H // 24
            base = residual[:ndays * 24].reshape(ndays, 24)
            hi = base.argmax(axis=1); lo = base.argmin(axis=1)
            rows_idx = np.arange(ndays)
            shift = np.minimum(dsr_mw, base[rows_idx, hi])          # MWh moved per day
            base[rows_idx, hi] -= shift                              # discharge (supply)
            base[rows_idx, lo] += shift                              # charge (load)
        dsr_series = residual_pre - residual  # +discharge at peak, -charge at trough; sum near 0

        # Thermal shape: residual load capped at total thermal capacity
        total_cap = merit_s.loc[merit_s.year == year, "capacity_mw"].sum()
        # aggregate thermal shape = residual capped at total thermal capacity
        thermal_shape_raw = np.clip(residual, 0.0, total_cap)
        if thermal_shape_raw.sum() <= 0:
            thermal_shape_raw = np.full(H, 1.0)  # degenerate (no residual): flat
        thermal_shape = thermal_shape_raw / thermal_shape_raw.sum()

        # Fuel generation from MBIE annual; CO2 from MBIE fuel use x MfE
        # Generation per fuel = MBIE annual GWh x thermal shape (reconciles exactly).
        # CO2 per fuel = MBIE published fuel input (Gross PJ) x MfE factor, distributed
        # over the same thermal shape. Heat rate is not used here (only for merit ranking).
        fuel_hourly, fuel_co2 = {}, {}
        for com in THERMAL_COMMODITIES:
            gwh = float(annual_gen.get(com, 0.0))
            co2_yr = combustion_co2_kg(scenario, year, com)  # kg/yr, MBIE fuel use x MfE
            if gwh <= 0 and co2_yr <= 0:
                continue
            fuel_hourly[com] = gwh * 1000.0 * thermal_shape       # MWh
            fuel_co2[com] = co2_yr * thermal_shape                # kg (annual sum = co2_yr)
            implied_ef = (co2_yr / (gwh * 1000.0)) if gwh > 0 else np.nan  # kg/MWh
            recon_log.append({"scenario": scenario, "year": year, "fuel": com,
                              "mbie_gwh": gwh, "model_gwh": fuel_hourly[com].sum() / 1000.0,
                              "fuel_use_pj": fuel_use_pj.get((scenario, year, com), 0.0),
                              "combustion_co2_kt": co2_yr / 1e6,
                              "combustion_co2_kt_precorrection": co2_yr / 1e6,  # unchanged (the
                                                                                # correction is Wood only)
                              "implied_ef_kg_per_mwh": implied_ef,
                              "flag": "MBIE_fueluse_x_MfE"})

        # Wood/biomass non-CO2 (CH4+N2O): tested and included.
        # MfE Table 3.4 (Biomass - Manufacturing Use, cited in edgs_common.py) gives a real,
        # non-biogenic CH4+N2O factor for wood combustion that combustion_co2_kg() does not
        # apply (Wood is a RENEWABLE_COMMODITY, outside the THERMAL_COMMODITIES loop above,
        # and its CO2 stays zero-rated/biogenic). Applied here to the same Wood fuel-use PJ
        # MBIE publishes and this pipeline uses for Wood generation: no new data source, no
        # blend/volume assumption. The figure without this term (0.0: wood CO2 is biogenic)
        # is kept in combustion_co2_kt_precorrection, same convention as the fossil rows
        # above, so both figures remain inspectable downstream.
        wood_co2_yr = wood_nonco2_kg(scenario, year)  # kg/yr, MBIE Wood fuel use x MfE Table 3.4
        wood_gwh = float(annual_gen.get("Wood", 0.0))
        if wood_co2_yr > 0 or wood_gwh > 0:
            wood_implied_ef = (wood_co2_yr / (wood_gwh * 1000.0)) if wood_gwh > 0 else np.nan
            recon_log.append({"scenario": scenario, "year": year, "fuel": "Wood",
                              "mbie_gwh": wood_gwh, "model_gwh": wood_gwh,  # renewable: MBIE-exact by construction
                              "fuel_use_pj": fuel_use_pj.get((scenario, year, "Wood"), 0.0),
                              "combustion_co2_kt": wood_co2_yr / 1e6,
                              "combustion_co2_kt_precorrection": 0.0,  # 0 without the non-CO2 term
                                                                       # (CO2 biogenic)
                              "implied_ef_kg_per_mwh": wood_implied_ef,
                              "flag": "MfE_Table3.4_wood_nonCO2_CH4_N2O_biogenic_CO2_excluded"})

        # Distribute the wood non-CO2 total across hours/islands using Wood's own generation
        # shape (same timing/island split as its MWh), consistent with how thermal CO2 above
        # uses the thermal shape, not an independent assumption.
        wood_nonco2_by_island = {"NI": np.zeros(H), "SI": np.zeros(H)}
        if wood_co2_yr > 0:
            wood_gen_total = sum(mwh.sum() for (isl, com), (mwh, fb) in ren_hourly.items() if com == "Wood")
            if wood_gen_total > 0:
                for (isl, com), (mwh, fb) in ren_hourly.items():
                    if com == "Wood":
                        wood_nonco2_by_island[isl] += wood_co2_yr * (mwh / wood_gen_total)

        # Geothermal fugitive CO2: tested, not included (see the Check-2 diagnostic).
        # A cited, capacity-weighted, time-varying geothermal factor (McLean & Richardson
        # 2019 field data, Ngawha=0 from 2024) was tested here. Adding it overshoots
        # MBIE's electricity GHG total by about 19-27% (emissions-weighted), worse than
        # combustion-only (about 6.3%). The regression's R2=0.9995 reflects geothermal
        # generation and the small residual rising together over the 27-year projection,
        # not a physical magnitude match (real geothermal CO2, about 0.6-0.9 Mt/yr, is
        # 2-4x the 0.05-0.4 Mt/yr gap it was meant to explain). See
        # README and build_edgs_check2_diagnostic.py. Not included in the CO2/EF calculation
        # below; geo_fleet_ef is retained only for the standalone diagnostic script.
        geo_co2_by_island = {"NI": np.zeros(H), "SI": np.zeros(H)}

        # DSR hourly net series computed above (Assumption 2 load-shift); net annual total near 0.
        dsr_hourly = dsr_series

        # Assemble generation rows
        for (isl, com), (mwh, fb) in ren_hourly.items():
            gen_rows.append(pd.DataFrame({
                "datetime_hour": dt, "scenario": scenario, "island": isl,
                "fuel_commodity": com, "generation_mwh": mwh,
                "source_tag": "MBIE_annual_disaggregated",
                "source_detail": ("Results!Electricity generation annual GWh x island cap "
                                  "share (Generation Stack) x hourly weight "
                                  "[assumption_1 central 2021, weekday-aligned]" + fb)}))
        for com, mwh in fuel_hourly.items():
            gen_rows.append(pd.DataFrame({
                "datetime_hour": dt, "scenario": scenario, "island": "NI",
                "fuel_commodity": com, "generation_mwh": mwh,
                "source_tag": "MBIE_annual_disaggregated",
                "source_detail": ("Results!Electricity generation annual GWh x thermal "
                                  "residual shape (merit order Module 3) [calculated]")}))
        if dsr_mw > 0:
            gen_rows.append(pd.DataFrame({
                "datetime_hour": dt, "scenario": scenario, "island": "NI",
                "fuel_commodity": "Demand side response", "generation_mwh": dsr_hourly,
                "source_tag": "assumption_2",
                "source_detail": ("Assumption 2 (model-original): DSR/battery daily peak-shave "
                                  f"load-shift at {dsr_mw:.0f} MW (GEM build schedule capacity); "
                                  "+ = discharge, - = charge; net annual ~0 (matches MBIE DSR net gen=0)")}))

        # Emission factor: fuel-input combustion + geothermal fugitive CO2
        #      + wood/biomass non-CO2 CH4+N2O
        # Per island: CO2 = thermal combustion (NI only, Module 3 and MBIE fuel input)
        # + geothermal fugitive (not included: geo_co2_by_island stays zero, see the comment
        # above) + wood non-CO2 (cited, MfE Table 3.4; Wood's CO2 remains biogenic/zero-rated,
        # only CH4+N2O added). MBIE's own electricity GHG target is compared in Module 6
        # (Check 2), not forced.
        island_co2 = {
            "NI": sum(fuel_co2.values()) + geo_co2_by_island["NI"] + wood_nonco2_by_island["NI"],  # kg
            "SI": geo_co2_by_island["SI"] + wood_nonco2_by_island["SI"],  # kg (0: no SI thermal or wood capacity)
        }
        island_gen = {
            "NI": island_ren_total["NI"] + sum(fuel_hourly.values()) + dsr_hourly,  # MWh
            "SI": island_ren_total["SI"],
        }
        for isl in ("NI", "SI"):
            with np.errstate(divide="ignore", invalid="ignore"):
                ef_isl = np.where(island_gen[isl] > 0, island_co2[isl] / (island_gen[isl] * 1000.0), 0.0)
            ef_rows.append(pd.DataFrame({
                "scenario": scenario, "island": isl, "datetime_hour": dt, "ef_basis": "generation",
                "emission_factor_kg_co2e_per_kwh": ef_isl, "reconciliation_flag": "pending"}))
        # Consumption-side EF, national: national CO2 / national delivered demand.
        # The generation-to-consumption gross-up factor embeds MBIE's own generation-demand
        # gap (about 7.7%): T&D losses, generator own-use and MBIE balancing items, not a pure
        # line-loss figure. Reported at national level because island consumption needs HVDC
        # allocation (the historical Consumption pipeline's method), out of scope here.
        national_co2 = island_co2["NI"] + island_co2["SI"]
        with np.errstate(divide="ignore", invalid="ignore"):
            cons_ef = np.where(_demand_cal > 0, national_co2 / (_demand_cal * 1000.0), 0.0)  # kg/kWh
        ef_rows.append(pd.DataFrame({
            "scenario": scenario, "island": "National", "datetime_hour": dt, "ef_basis": "consumption",
            "emission_factor_kg_co2e_per_kwh": cons_ef, "reconciliation_flag": "pending"}))

    log(f"  {scenario}: dispatched {len(YEARS)} years")

# Write
gen = pd.concat(gen_rows, ignore_index=True)
ef = pd.concat(ef_rows, ignore_index=True)
recon = pd.DataFrame(recon_log)
peaks = pd.DataFrame(peak_log)

suffix = "" if set(run_scenarios) == set(SCENARIOS) else "_" + "_".join(run_scenarios)
if CENTRAL_TEMPLATE != 2021:
    suffix += f"_tmpl{CENTRAL_TEMPLATE}"
gen.to_parquet(OUT_DIR / f"edgs_hourly_generation{suffix}.parquet", index=False)
ef.to_parquet(OUT_DIR / f"edgs_hourly_emission_factor{suffix}.parquet", index=False)
recon.to_parquet(OUT_DIR / f"edgs_thermal_intensity{suffix}.parquet", index=False)
peaks.to_parquet(OUT_DIR / f"edgs_peak_calibration{suffix}.parquet", index=False)

peaks["err_pct"] = (peaks["model_peak_gw"] / peaks["mbie_peak_gw"] - 1) * 100
log(f"\nGeneration rows: {len(gen):,}; EF rows: {len(ef):,}")
log(f"Peak calibration error: max |{peaks['err_pct'].abs().max():.3f}%| (target 0)")
log(f"Thermal fuel-years reconciled exactly by construction: {len(recon)}")
log(f"Wrote edgs_hourly_generation{suffix}.parquet and edgs_hourly_emission_factor{suffix}.parquet")
(OUT_DIR / f"processing_log_dispatch{suffix}.txt").write_text("\n".join(lines), encoding="utf-8")
