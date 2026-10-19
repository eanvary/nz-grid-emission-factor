"""
Follow-up brief C — is the HVDC capacity violation (Brief B, Step 5: 103/135 scenario-years,
up to 2,662 MW by 2050 vs the cited 1,200 MW Cook Strait capacity) a genuine finding or an
artifact of this pipeline's own simplifications? Tests three candidate artifacts as genuine
re-runs (not qualitative reasoning), each producing a comparable violation count/magnitude to
the BASELINE (Module 7's shipped result), then a COMBINED re-run with all three fixes together.

  Sensitivity A (Step 2) — DSR/battery island split: currently 100% of DSR net effect is
    booked to NI (edgs_hourly_generation.parquet); GEM build schedule capacity is actually
    ~48/52 NI/SI (Reference/Growth/Constraint/Environmental: 244.8 NI / 266.6 SI MW;
    Innovation: 244.8 NI / 248.8 SI MW). Re-allocates the EXISTING national DSR hourly
    series by each scenario-year's GEM capacity share (a documented approximation: the
    peak-shave TIMING pattern stays national/residual-driven, only the ISLAND SPLIT of that
    pattern changes - a full independent per-island DSR re-dispatch is out of scope here).
  Sensitivity B (Step 3) — solar shape artifact: the raw EA/EMI data has no Solar fuel code
    before 2024 (Brief B finding), so the shipped central template (2021) falls back to a
    flat 24-hour profile. Re-runs using the 2024 template's REAL diurnal solar shape for
    both islands instead.
  Sensitivity C (Step 4) — uniform loss-ratio bounding: Module 7's actual (corrected)
    formula renormalises island generation-level load to real national generation, so the
    national loss/gross-up ratio CANCELS OUT of the island split and does not directly
    drive the transfer magnitude. To give this simplification a genuine test, a
    DIFFERENTIAL (not uniform) NI-vs-SI loss adjustment is applied to the pre-renormalisation
    island shares (+/-10%, explicitly a bounding/illustrative magnitude, not a cited or
    claimed-true value - no island-specific loss data exists, per Brief B) in both
    directions (NI-heavier and SI-heavier), reasoning stated in the README.

Outputs: edgs_hvdc_sensitivity_summary.csv (baseline + 5 sensitivity variants x scenario)

TEMPLATE PARAMETERISATION (2026-08-12, Brief N / PLAN_11YEAR_TEMPLATE_REASSESSMENT.md Step 7):
set EDGS_TEMPLATE_YEAR to re-derive this brief's baseline+sensitivities against a different
Assumption-1 shape template (e.g. 2017, the true 11-year median) instead of the shipped 2021
central template. Reads the matching edgs_hourly_generation{_tmplYYYY}.parquet /
edgs_hourly_emission_factor{_tmplYYYY}.parquet (produced by build_edgs_dispatch.py with the
same env var) and filters demand/renewable shapes to that template year. Output filename
gets the same suffix, so the shipped central-template CSV is never overwritten.
"""
import os
import numpy as np
import pandas as pd

from edgs_common import ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, log_factory

log, lines = log_factory()
HVDC_CAPACITY_MW = 1200.0
TEMPLATE_YEAR = int(os.environ.get("EDGS_TEMPLATE_YEAR", "2021"))
SUFFIX = "" if TEMPLATE_YEAR == 2021 else f"_tmpl{TEMPLATE_YEAR}"
log(f"Template year: {TEMPLATE_YEAR} (suffix '{SUFFIX}')")

targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
dem_shape_all = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
gen = pd.read_parquet(OUT_DIR / f"edgs_hourly_generation{SUFFIX}.parquet")
gen["year"] = pd.to_datetime(gen["datetime_hour"]).dt.year
ef = pd.read_parquet(OUT_DIR / f"edgs_hourly_emission_factor{SUFFIX}.parquet")
ef["year"] = pd.to_datetime(ef["datetime_hour"]).dt.year
gem = pd.read_parquet(OUT_DIR / "edgs_gem_build.parquet")
ren_shape = pd.read_parquet(OUT_DIR / "edgs_shape_renewables.parquet")

isd = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Island share of demand")
isd = isd[isd["Variable"] == "North Island share of national demand"]
ni_share_map = isd.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()

dem_shape_2021 = dem_shape_all[dem_shape_all.template_year == TEMPLATE_YEAR]

# DSR GEM capacity share per scenario
dsr_gem = gem[gem.commodity == "Demand side response"]
dsr_share = {}
for sc in SCENARIOS:
    s = dsr_gem[dsr_gem.scenario == sc].groupby("island")["capacity_mw"].sum()
    tot = s.sum()
    dsr_share[sc] = {"NI": s.get("NI", 0) / tot if tot else 0.5, "SI": s.get("SI", 0) / tot if tot else 0.5}
log("DSR GEM capacity share by scenario: " + str({k: {i: round(v, 3) for i, v in d.items()} for k, d in dsr_share.items()}))

# 2024 solar shape (real, both islands available? check)
sol_2024 = ren_shape[(ren_shape.template_year == 2024) & (ren_shape.fuel_std == "SOL")]
log(f"2024 solar shape rows: {len(sol_2024)}, islands: {sorted(sol_2024.island.unique())}")
w2024_solar = sol_2024[sol_2024.island == "NI"][["month", "day", "hour", "weight"]]  # only NI has 2024 data


def year_calendar(year):
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return pd.DataFrame({"datetime_hour": idx, "month": idx.month, "day": idx.day, "hour": idx.hour})


def map_weights(cal, wtab):
    m = cal.merge(wtab, on=["month", "day", "hour"], how="left")
    w = m["weight"].fillna(0.0).to_numpy()
    s = w.sum()
    return w / s if s > 0 else w


w_ni_base = dem_shape_2021[dem_shape_2021.island == "NI"][["month", "day", "hour", "weight"]]
w_si_base = dem_shape_2021[dem_shape_2021.island == "SI"][["month", "day", "hour", "weight"]]

# ---------------------------------------------------------------------------
# PERFORMANCE: pre-group the 16.5M-row generation table ONCE, by (scenario,year,island)
# total generation and (scenario,year) DSR/Solar-by-island series, instead of re-filtering
# the full table on every one of the ~1000+ calls the naive per-scenario-year loop makes.
# ---------------------------------------------------------------------------
log("Pre-grouping generation table (one pass)...")
totgen_by_sy_isl = (gen.groupby(["scenario", "year", "island", "datetime_hour"])["generation_mwh"]
                    .sum().unstack("datetime_hour"))
dsr_by_sy = (gen[gen.fuel_commodity == "Demand side response"]
            .groupby(["scenario", "year", "datetime_hour"])["generation_mwh"].sum().unstack("datetime_hour"))
solar_by_sy_isl = (gen[gen.fuel_commodity == "Solar"]
                  .groupby(["scenario", "year", "island", "datetime_hour"])["generation_mwh"]
                  .sum().unstack("datetime_hour"))
log("  done.")


def lookup_gen(scenario, year, island, dt):
    try:
        s = totgen_by_sy_isl.loc[(scenario, year, island)]
        return s.reindex(dt, fill_value=0.0).to_numpy()
    except KeyError:
        return np.zeros(len(dt))


def compute_transfer(dt, ni_share, w_ni, w_si, g_NI, g_SI, gNI_adj=None, gSI_adj=None, ni_delta=0.0, si_delta=0.0):
    """Core Module 7 Step1-3 arithmetic, given precomputed per-island generation, with
    optional per-hour generation adjustments (gNI_adj/gSI_adj, for the DSR and solar
    sensitivities) and optional differential loss adjustment (ni_delta/si_delta, for the
    loss-ratio bounding sensitivity)."""
    if gNI_adj is not None:
        g_NI = g_NI + gNI_adj
    if gSI_adj is not None:
        g_SI = g_SI + gSI_adj
    nat_gen = g_NI + g_SI

    # The fallback mask is determined from the UNDELTA'D (base) shape only - matching
    # Module 7's own `share_sum <= 0` check exactly - so every sensitivity variant uses the
    # SAME fallback hour(s) consistently, and the baseline (ni_delta=si_delta=0) reproduces
    # Module 7's shipped result exactly. Applying delta scaling BEFORE determining the mask
    # let a single historical-data anomaly (one DST-transition hour with a genuinely negative
    # raw component weight - a documented artifact, not a bug) cross from a safely-negative
    # base sum to a tiny-positive delta-scaled sum, evading the mask and causing a
    # near-zero-division artifact (confirmed: max transfer 2.69 MILLION MW at
    # Innovation/2027 before this fix) - a bug in this diagnostic script's delta test, not
    # in the shipped Module 7 output (whose unscaled base sum is safely negative there).
    base_ssum = ni_share * w_ni + (1 - ni_share) * w_si
    no_shape = base_ssum <= 0

    raw_ni = ni_share * w_ni * (1 + ni_delta)
    raw_si = (1 - ni_share) * w_si * (1 + si_delta)
    if no_shape.any():
        raw_ni = np.where(no_shape, ni_share, raw_ni)
        raw_si = np.where(no_shape, 1 - ni_share, raw_si)
    ssum = raw_ni + raw_si
    gl_NI = nat_gen * raw_ni / ssum
    tr_NI = gl_NI - g_NI
    return tr_NI


def dsr_series_for(scenario, year, dt):
    try:
        return dsr_by_sy.loc[(scenario, year)].reindex(dt, fill_value=0.0).to_numpy()
    except KeyError:
        return None


def solar_adjustment_for(scenario, year, dt):
    """Return (gNI_delta, gSI_delta) = 2024-shape solar minus flat-baseload solar, per island."""
    t = targets[(targets.scenario == scenario) & (targets.year == year) & (targets.metric == "net_generation")
               & (targets.commodity == "Solar")]
    gwh = float(t["value"].iloc[0]) if len(t) else 0.0
    if gwh <= 0:
        return np.zeros(len(dt)), np.zeros(len(dt))
    try:
        cur_NI = solar_by_sy_isl.loc[(scenario, year, "NI")].reindex(dt, fill_value=0.0).to_numpy()
    except KeyError:
        cur_NI = np.zeros(len(dt))
    try:
        cur_SI = solar_by_sy_isl.loc[(scenario, year, "SI")].reindex(dt, fill_value=0.0).to_numpy()
    except KeyError:
        cur_SI = np.zeros(len(dt))
    share_NI = cur_NI.sum() / (cur_NI.sum() + cur_SI.sum()) if (cur_NI.sum() + cur_SI.sum()) > 0 else 0.5
    cal = pd.DataFrame({"datetime_hour": dt, "month": pd.DatetimeIndex(dt).month,
                        "day": pd.DatetimeIndex(dt).day, "hour": pd.DatetimeIndex(dt).hour})
    w = map_weights(cal, w2024_solar)
    new_NI = gwh * 1000.0 * share_NI * w
    new_SI = gwh * 1000.0 * (1 - share_NI) * w
    return new_NI - cur_NI, new_SI - cur_SI


# ---------------------------------------------------------------------------
# Run baseline + sensitivities for all 135 scenario-years (using precomputed lookups)
# ---------------------------------------------------------------------------
def flag(tr):
    return np.abs(tr).max(), int((np.abs(tr) > HVDC_CAPACITY_MW).sum())


rows = []
cal_cache = {}
for scenario in SCENARIOS:
    for year in YEARS:
        if year not in cal_cache:
            cal = year_calendar(year)
            cal_cache[year] = (cal, cal["datetime_hour"].to_numpy(),
                              map_weights(cal, w_ni_base), map_weights(cal, w_si_base))
        cal, dt, w_ni, w_si = cal_cache[year]
        ni_share = float(ni_share_map.get((scenario, year), 0.61))
        g_NI = lookup_gen(scenario, year, "NI", dt)
        g_SI = lookup_gen(scenario, year, "SI", dt)

        # --- BASELINE ---
        tr_base = compute_transfer(dt, ni_share, w_ni, w_si, g_NI, g_SI)
        max_base, n_base = flag(tr_base)

        # --- Sensitivity A: DSR split 48/52 (GEM) instead of 100% NI ---
        dsr_vals = dsr_series_for(scenario, year, dt)
        if dsr_vals is not None:
            share = dsr_share[scenario]
            gNI_adj = dsr_vals * (share["NI"] - 1.0)   # remove 100%, add back NI share
            gSI_adj = dsr_vals * share["SI"]             # add SI's share
        else:
            gNI_adj = gSI_adj = np.zeros(len(dt))
        tr_a = compute_transfer(dt, ni_share, w_ni, w_si, g_NI, g_SI, gNI_adj=gNI_adj, gSI_adj=gSI_adj)
        max_a, n_a = flag(tr_a)

        # --- Sensitivity B: real 2024 solar shape instead of flat baseload ---
        sNI, sSI = solar_adjustment_for(scenario, year, dt)
        tr_b = compute_transfer(dt, ni_share, w_ni, w_si, g_NI, g_SI, gNI_adj=sNI, gSI_adj=sSI)
        max_b, n_b = flag(tr_b)

        # --- Sensitivity C: loss-differential bounding, +/-10% ---
        tr_c1 = compute_transfer(dt, ni_share, w_ni, w_si, g_NI, g_SI, ni_delta=+0.10, si_delta=0.0)
        tr_c2 = compute_transfer(dt, ni_share, w_ni, w_si, g_NI, g_SI, ni_delta=0.0, si_delta=+0.10)
        max_c1, n_c1 = flag(tr_c1)
        max_c2, n_c2 = flag(tr_c2)

        # --- COMBINED: A + B together ---
        tr_comb = compute_transfer(dt, ni_share, w_ni, w_si, g_NI, g_SI,
                                   gNI_adj=gNI_adj + sNI, gSI_adj=gSI_adj + sSI)
        max_comb, n_comb = flag(tr_comb)

        rows.append({"scenario": scenario, "year": year,
                    "max_mw_baseline": max_base, "n_hours_baseline": n_base,
                    "max_mw_dsr_split": max_a, "n_hours_dsr_split": n_a,
                    "max_mw_solar_fix": max_b, "n_hours_solar_fix": n_b,
                    "max_mw_loss_NIup": max_c1, "n_hours_loss_NIup": n_c1,
                    "max_mw_loss_SIup": max_c2, "n_hours_loss_SIup": n_c2,
                    "max_mw_combined": max_comb, "n_hours_combined": n_comb})
    log(f"  {scenario}: done")

df = pd.DataFrame(rows)
df.to_csv(OUT_DIR / f"edgs_hvdc_sensitivity_summary{SUFFIX}.csv", index=False)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log("\n=== HVDC capacity violation sensitivity summary (135 scenario-years) ===")
for tag, maxcol, ncol in [
    ("BASELINE (Module 7 shipped)", "max_mw_baseline", "n_hours_baseline"),
    ("A: DSR 48/52 split", "max_mw_dsr_split", "n_hours_dsr_split"),
    ("B: real 2024 solar shape", "max_mw_solar_fix", "n_hours_solar_fix"),
    ("C1: loss +10% NI", "max_mw_loss_NIup", "n_hours_loss_NIup"),
    ("C2: loss +10% SI", "max_mw_loss_SIup", "n_hours_loss_SIup"),
    ("COMBINED (A+B)", "max_mw_combined", "n_hours_combined"),
]:
    n_sy_flagged = (df[maxcol] > HVDC_CAPACITY_MW).sum()
    log(f"  {tag:30s}: {n_sy_flagged}/135 scenario-years flagged, "
        f"max transfer overall = {df[maxcol].max():.0f} MW, "
        f"total flagged hours = {df[ncol].sum()}")

log(f"\nWrote edgs_hvdc_sensitivity_summary{SUFFIX}.csv")
(OUT_DIR / f"processing_log_hvdc_sensitivity{SUFFIX}.txt").write_text("\n".join(lines), encoding="utf-8")
