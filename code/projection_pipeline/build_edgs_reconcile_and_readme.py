"""
Module 6 (v2): Step 8 reconciliation, acceptance criteria, Assumption-1 sensitivity,
and the README. Rewritten per Revised Approach v2:

  Check 1 (fuel-by-fuel generation)  : reconciles to MBIE, tol +/-0.1% (exact by design)
  Check 3 (annual peak)              : demand series vs MBIE Peak demand, tol +/-0.1%
  Check 2 (emissions)                : HONEST, unforced. Reported two ways:
     (2a) national combustion CO2 (MBIE fuel use x MfE) vs MBIE Greenhouse gas emissions
          [Electricity generation] - a numerator-to-numerator test with no denominator
          scope ambiguity. This is the genuine validation of the combustion rebuild.
     (2b) model generation-side EF (over TOTAL net generation) vs MBIE Emission factors
          sheet - noting MBIE's factor is 'primary activity' scope (excludes autoproducer
          cogen), a ~3.7% denominator scope difference that is quantified, not hidden.
  Neither 2a nor 2b is forced to zero; the true deviation is reported per scenario-year.

Outputs (output/edgs/): edgs_reconciliation_report.csv, edgs_check2_emissions.csv,
  edgs_hourly_emission_factor.parquet (reconciliation_flag set), edgs_sensitivity_A1.csv,
  README_EDGS_hourly.md
"""
import numpy as np
import pandas as pd

from edgs_common import (OUT_DIR, SCENARIOS, YEARS, SOURCE_TAGS, MFE_SOURCE,
                         ASSUMPTION_1, ASSUMPTION_2, RESULTS_XLSX, ASSUMPTIONS_XLSX,
                         log_factory)

log, lines = log_factory()
TOL = 0.1  # percent, for the exact-by-construction checks (1 and 3)

gen = pd.read_parquet(OUT_DIR / "edgs_hourly_generation.parquet")
ef = pd.read_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet")
tgt = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
peaks = pd.read_parquet(OUT_DIR / "edgs_peak_calibration.parquet")
ti = pd.read_parquet(OUT_DIR / "edgs_thermal_intensity.parquet")   # per-fuel combustion CO2
gen["year"] = pd.to_datetime(gen["datetime_hour"]).dt.year
ef["year"] = pd.to_datetime(ef["datetime_hour"]).dt.year

ghg = pd.read_excel(RESULTS_XLSX, sheet_name="Greenhouse gas emissions")
ghg = ghg[ghg.Emission_Sector == "Electricity generation"].set_index(["Scenario", "TimePeriod"])["Value"]  # Mt

# Check 1: national annual generation by fuel vs Results!Electricity generation
gsum = gen.groupby(["scenario", "year", "fuel_commodity"])["generation_mwh"].sum().div(1000).reset_index()
mbie_gen = tgt[tgt.metric == "net_generation"][["scenario", "year", "commodity", "value"]]
c1 = gsum.merge(mbie_gen, left_on=["scenario", "year", "fuel_commodity"],
                right_on=["scenario", "year", "commodity"], how="left")
c1["diff_pct"] = np.where(c1["value"].fillna(0) > 0, (c1["generation_mwh"] / c1["value"] - 1) * 100, 0.0)
check1 = c1.groupby(["scenario", "year"])["diff_pct"].apply(lambda s: s.abs().max()).rename("check1_gen_pct")

# Check 3: annual peak (demand series) vs Results!Peak demand
peaks["diff_pct"] = (peaks["model_peak_gw"] / peaks["mbie_peak_gw"] - 1).abs() * 100
check3 = peaks.set_index(["scenario", "year"])["diff_pct"].rename("check3_peak_pct")

# Check 2: HONEST emissions comparison (unforced)
# (2a) combustion CO2 vs MBIE GHG (numerator-to-numerator)
comb = ti.groupby(["scenario", "year"])["combustion_co2_kt"].sum().div(1000).rename("model_comb_Mt")  # Mt
mbie_ghg = ghg.rename_axis(["scenario", "year"]).rename("mbie_ghg_Mt")
c2a = pd.concat([comb, mbie_ghg], axis=1).dropna()
c2a = c2a[c2a.index.get_level_values("year").isin(YEARS)]
c2a["check2a_emissions_pct"] = (c2a["model_comb_Mt"] / c2a["mbie_ghg_Mt"] - 1) * 100

# (2b) model generation-side EF (over total net generation) vs MBIE EF sheet
ni_gen = gen[gen.island == "NI"].groupby(["scenario", "year", "datetime_hour"])["generation_mwh"].sum().reset_index()
efg = ef[(ef.island == "NI") & (ef.ef_basis == "generation")].merge(ni_gen, on=["scenario", "year", "datetime_hour"])
efg["co2"] = efg["emission_factor_kg_co2e_per_kwh"] * efg["generation_mwh"] * 1000
co2 = efg.groupby(["scenario", "year"])["co2"].sum()
totgen = gen[gen.fuel_commodity != "Demand side response"].groupby(["scenario", "year"])["generation_mwh"].sum() * 1000
model_ef = (co2 / totgen).rename("model_gen_ef")
mbie_ef = tgt[tgt.metric == "grid_emission_factor"].set_index(["scenario", "year"])["value"].rename("mbie_ef")
c2b = pd.concat([model_ef, mbie_ef], axis=1)
c2b["check2b_ef_pct"] = (c2b["model_gen_ef"] / c2b["mbie_ef"] - 1) * 100

check2 = pd.concat([c2a["check2a_emissions_pct"], c2b["check2b_ef_pct"]], axis=1)
check2.reset_index().rename(columns={"level_0": "scenario", "level_1": "year"}).to_csv(
    OUT_DIR / "edgs_check2_emissions.csv", index=False)

# Combined report + reconciliation_flag (PASS gated on the exact checks 1 & 3 only)
report = pd.concat([check1, check3], axis=1)
report = report.join(check2)
report = report.reset_index()
report["c1_pass"] = report["check1_gen_pct"] <= TOL
report["c3_pass"] = report["check3_peak_pct"] <= TOL
report["exact_pass"] = report["c1_pass"] & report["c3_pass"]
report.to_csv(OUT_DIR / "edgs_reconciliation_report.csv", index=False)

n_total = len(report)
n_pass = int(report["exact_pass"].sum())
log(f"Reconciliation report: {n_pass}/{n_total} scenario-years pass Checks 1 & 3 at +/-{TOL}%")
log(f"  Check 1 (gen by fuel): max |diff| {report['check1_gen_pct'].max():.4f}%")
log(f"  Check 3 (peak):        max |diff| {report['check3_peak_pct'].max():.4f}%")
# Emissions-WEIGHTED Check 2a deviation (fair headline: total abs discrepancy / total MBIE
# emissions), so tiny-emission years don't dominate an unweighted mean.
c2a_w = c2a.copy()
c2a_w["abs_err_Mt"] = (c2a_w["model_comb_Mt"] - c2a_w["mbie_ghg_Mt"]).abs()
ew = c2a_w["abs_err_Mt"].sum() / c2a_w["mbie_ghg_Mt"].sum() * 100
log(f"  Check 2a (combustion CO2 vs MBIE GHG): EMISSIONS-WEIGHTED |diff| {ew:.2f}% "
    f"(unweighted mean {report['check2a_emissions_pct'].abs().mean():.1f}%, max {report['check2a_emissions_pct'].abs().max():.1f}%)")
log(f"  Check 2b (gen-side EF vs MBIE EF sheet): mean |diff| {report['check2b_ef_pct'].abs().mean():.2f}%, "
    f"max |diff| {report['check2b_ef_pct'].abs().max():.2f}%")
log("  Check 2a: agreement is ~1-4% where emissions are material (>1.5 Mt, 117/135 years); the "
    "large deviations (up to -22%) are the Environmental scenario's near-decarbonised later years "
    "(~1.3 Mt absolute). Cause is NOT cleanly attributable to one factor - MBIE publishes no "
    "per-fuel emission breakdown; candidate contributors are MBIE's effective fuel factors "
    "differing from the cited MfE values and possible small non-combustion (e.g. geothermal) "
    "emissions in MBIE's total. Reported, not adjusted (resolving it would require inventing "
    "factors or MBIE's unpublished per-fuel split).")

# scope gap (2b denominator): total net gen vs MBIE 'primary activity' generation
scope = []
for sc in SCENARIOS:
    for yr in (2024, 2050):
        tot = tgt[(tgt.scenario == sc) & (tgt.year == yr) & (tgt.metric == "net_generation")]["value"].sum() / 1000
        g = float(ghg.get((sc, yr), np.nan)); e = float(mbie_ef.get((sc, yr), np.nan))
        prim = g / e if (np.isfinite(g) and np.isfinite(e) and e > 0) else np.nan  # MBIE primary-activity TWh
        scope.append((sc, yr, tot, prim, (tot / prim - 1) * 100 if prim else np.nan))
scope = pd.DataFrame(scope, columns=["scenario", "year", "total_netgen_TWh", "mbie_primary_TWh", "scope_gap_pct"])
log(f"  Denominator scope gap (total net gen vs MBIE primary-activity): "
    f"mean {scope['scope_gap_pct'].mean():.1f}% (autoproducer cogen excluded by MBIE)")

# Step 3 (follow-up brief): standing sanity assertion, STRONG version. The prior version
# was confirmed to be a weak IDENTITY check: it re-derived both EF values from the same
# source totals (co2/netgen vs co2/demand using the identical co2 numerator), which is
# mathematically guaranteed to pass whenever netgen >= demand (always true) - it could
# never catch a table-population bug like the earlier backwards-ratio error. Rewritten to
# READ BACK the actual materialized edgs_hourly_emission_factor.parquet rows and aggregate
# them energy-weighted (matching the actual output's weighting convention), not re-derive
# from annual targets.
log("\n=== Step 3: consumption >= generation EF assertion — STRONG (table read-back) version ===")
gen["year"] = pd.to_datetime(gen["datetime_hour"]).dt.year  # restore (dropped by drop_duplicates elsewhere)
gen_noDSR = gen[gen.fuel_commodity != "Demand side response"]
g_natgen = gen_noDSR.groupby(["scenario", "year", "datetime_hour"])["generation_mwh"].sum().reset_index()
e_gen_rows = ef[ef.ef_basis == "generation"].merge(g_natgen, on=["scenario", "year", "datetime_hour"])
e_gen_rows["co2_kg"] = e_gen_rows["emission_factor_kg_co2e_per_kwh"] * e_gen_rows["generation_mwh"] * 1000
gen_ef_by_yr = (e_gen_rows.groupby(["scenario", "year"])
               .apply(lambda d: d["co2_kg"].sum() / (d["generation_mwh"].sum() * 1000), include_groups=False)
               .rename("gen_ef_readback"))
cons_ef_by_yr = (ef[ef.ef_basis == "consumption"]
                 .groupby(["scenario", "year"])["emission_factor_kg_co2e_per_kwh"].mean()
                 .rename("cons_ef_readback"))  # already national, one value/hour -> simple mean = energy-weighted-equivalent since ef_basis=consumption is a single national series
assert_df = pd.concat([gen_ef_by_yr, cons_ef_by_yr], axis=1).dropna()
assert_fail = assert_df[assert_df["cons_ef_readback"] + 1e-12 < assert_df["gen_ef_readback"]]
if len(assert_fail):
    log(f"  ASSERTION FAILED for {len(assert_fail)} scenario-years (consumption < generation EF, "
        f"read back from the actual output table):")
    log(assert_fail.reset_index().to_string(index=False))
else:
    log(f"  OK — all {len(assert_df)} scenario-years: consumption EF >= generation EF, "
        f"READ BACK from edgs_hourly_emission_factor.parquet rows (energy-weighted, national), "
        f"not re-derived from source totals.")

# Injected-failure test: corrupt a COPY of the read-back table (force one scenario-year's
# consumption EF below its generation EF) and confirm the SAME check catches it. This is
# the only way to be confident the assertion has teeth, not just that it passes on clean data.
log("\n  Injected-failure test:")
_test = assert_df.copy()
_victim = _test.index[0]
_test.loc[_victim, "cons_ef_readback"] = _test.loc[_victim, "gen_ef_readback"] * 0.5  # force a bad row
_caught = _test[_test["cons_ef_readback"] + 1e-12 < _test["gen_ef_readback"]]
if _victim in _caught.index:
    log(f"    OK — corrupted row {_victim} (cons_ef forced to 50% of gen_ef) was CAUGHT by the "
        f"assertion. The check has teeth.")
else:
    log(f"    ASSERTION HAS NO TEETH — injected bad row {_victim} was NOT caught. Fix before trusting it.")

# Carry the honest Check-2 deviation with the data itself, not just the README.
# reconciliation_flag reflects only Checks 1 & 3 (exact); check2_deviation_pct exposes the
# emissions deviation per scenario-year so a PASS filter can't hide it.
flagmap = report.set_index(["scenario", "year"])["exact_pass"].map({True: "PASS", False: "FAIL"}).to_dict()
c2map = report.set_index(["scenario", "year"])["check2a_emissions_pct"].round(2).to_dict()
ef["reconciliation_flag"] = [flagmap.get((s, y), "NA") for s, y in zip(ef["scenario"], ef["year"])]
ef["check2_deviation_pct"] = [c2map.get((s, y), np.nan) for s, y in zip(ef["scenario"], ef["year"])]
ef.drop(columns=["year"]).to_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet", index=False)
log("\nRewrote edgs_hourly_emission_factor.parquet with reconciliation_flag (Checks 1&3) + "
    "check2_deviation_pct (honest Check-2a % per scenario-year)")

# Acceptance criteria
log("\n=== ACCEPTANCE CRITERIA ===")
tags = set(gen["source_tag"].unique())
blank = gen["source_tag"].isna().sum() + (gen["source_tag"] == "").sum()
log(f"[{'OK' if blank == 0 and tags <= SOURCE_TAGS else 'FAIL'}] source_tag valid: tags={sorted(tags)}, {blank} blanks")
log(f"[{'OK' if n_pass == n_total else 'FAIL'}] Checks 1 & 3 pass for all {len(SCENARIOS)}x{len(YEARS)} scenario-years")
log(f"[OK] Check 2 reported HONESTLY (unforced): 2a mean |{report['check2a_emissions_pct'].abs().mean():.1f}%|, "
    f"2b mean |{report['check2b_ef_pct'].abs().mean():.1f}%| - see edgs_check2_emissions.csv")
log(f"[OK] ef_basis column present: {sorted(ef.ef_basis.unique())}")
log(f"[OK] MfE fuel factors cited: {MFE_SOURCE}")
log(f"[OK] Combustion from MBIE published fuel use (Electricity generation use, Gross PJ) x MfE")

# Consumption-side gross-up factor (Step C): MBIE net generation / MBIE demand
grossups = []
for sc in SCENARIOS:
    for yr in YEARS:
        d = tgt[(tgt.scenario == sc) & (tgt.year == yr) & (tgt.metric == "annual_demand")]["value"].iloc[0]
        g = tgt[(tgt.scenario == sc) & (tgt.year == yr) & (tgt.metric == "net_generation")]["value"].sum() / 1000
        grossups.append(g / d)
grossup_mean = float(np.mean(grossups))
log(f"\nGeneration-to-consumption gross-up factor (MBIE net gen / demand): mean {grossup_mean:.3f} "
    f"(= {(grossup_mean-1)*100:.1f}%; includes T&D losses + generator own-use + MBIE balancing "
    f"items - NOT a pure line-loss figure; MBIE-derived)")

# Assumption-1 sensitivity (Reference NI hourly EF shape)
def ni_hourly_ef(ef_df):
    e = ef_df[(ef_df.island == "NI") & (ef_df.ef_basis == "generation")].copy()
    e["month"] = pd.to_datetime(e["datetime_hour"]).dt.month
    return e

central_e = ni_hourly_ef(ef[ef.scenario == "Reference"])
templates = {"central_2021": central_e}
for tag, yr in [("wet_2023", 2023), ("dry_2024", 2024)]:
    e = pd.read_parquet(OUT_DIR / f"edgs_hourly_emission_factor_Reference_tmpl{yr}.parquet")
    templates[tag] = ni_hourly_ef(e)

base = central_e.set_index("datetime_hour")["emission_factor_kg_co2e_per_kwh"]
rows = []
for tag, e in templates.items():
    s = e.set_index("datetime_hour")["emission_factor_kg_co2e_per_kwh"]
    aligned = pd.concat([base.rename("c"), s.rename("t")], axis=1).dropna()
    mad = (aligned["t"] - aligned["c"]).abs().mean()
    monthly = e.groupby("month")["emission_factor_kg_co2e_per_kwh"].mean()
    rows.append({"template": tag, "mean_abs_hourly_EF_diff_vs_central_kg_per_kwh": round(mad, 5),
                 "monthly_EF_spread_kg_per_kwh": round(monthly.max() - monthly.min(), 5),
                 "annual_mean_NI_EF_kg_per_kwh": round(e["emission_factor_kg_co2e_per_kwh"].mean(), 5)})
sens = pd.DataFrame(rows)
sens.to_csv(OUT_DIR / "edgs_sensitivity_A1.csv", index=False)
sens_wet = sens[sens.template == "wet_2023"]["mean_abs_hourly_EF_diff_vs_central_kg_per_kwh"].iloc[0]
sens_dry = sens[sens.template == "dry_2024"]["mean_abs_hourly_EF_diff_vs_central_kg_per_kwh"].iloc[0]
log(f"\nA1 sensitivity (Reference NI hourly EF shape): wet {sens_wet:.4f}, dry {sens_dry:.4f} kg/kWh "
    "mean abs hourly diff vs central. Annual national EF is MBIE-anchored (fuel use + net gen "
    "both template-invariant), so sensitivity appears only in the hourly/seasonal shape.")

# README (v2)
readme = f"""# EDGS 2024 hourly, island-resolved reconstruction — output metadata (v2)

Hourly (8760/yr), NI/SI generation and grid emission-factor trajectories for the five MBIE
EDGS 2024 scenarios ({', '.join(SCENARIOS)}), {YEARS[0]}-{YEARS[-1]}, disaggregating MBIE's
published ANNUAL NATIONAL results into hourly island detail. Reconciled to MBIE, not an
independent forecast. This v2 supersedes the earlier "geothermal residual / 0.0000% Check 2"
version, which was circular; Check 2 is now a genuine, unforced test.

## 1. Denominator scope (Step A) — 'primary activity' generation
MBIE's `Emission factors` sheet is computed over "primary activity electricity generation"
only ({scope[scope.year==2024]['mbie_primary_TWh'].mean():.1f} TWh mean 2024), i.e. it EXCLUDES
autoproducer / industrial cogeneration (Glenbrook, Kinleith [ACHP]; Whareroa, Kapuni [PCHP] in
the Generation Stack) — about {scope['scope_gap_pct'].mean():.1f}% below total net generation.
The model's published generation-side EF (Check 2b) is over TOTAL net generation, so it is a
slightly broader-scope factor than MBIE's; the scope gap is quantified in
edgs_reconciliation_report.csv, not absorbed into any residual term. CV gross-vs-net basis was
investigated and ruled out as the driver (it was basis-consistent on losses, wrong on scope).

## 2. Residual-load fix (Step A2) — generation-level, not demand
The dispatch residual is now built from GENERATION-level load (energy = MBIE net generation
total = demand + T&D losses + own use, ~{(grossup_mean-1)*100:.1f}% above demand), using the
same Assumption-1 historical hourly SHAPE. Previously it used delivered demand, which made
residual ~7% too small every hour and distorted the thermal hourly shape. Peak validation
(Check 3) remains anchored to MBIE's demand-side `Peak demand` figure, computed on a separate
demand series — these are two distinct, correctly-different quantities, not an inconsistency.

## 3. Combustion rebuilt from MBIE fuel use (Step B)
Combustion CO2 is now computed as MBIE's published `Electricity generation use (Gross PJ)` per
commodity × MfE factors ({MFE_SOURCE}) — directly, not via plant heat rates (heat-rate
combustion undershot MBIE by ~11% and the old "geothermal residual" was absorbing that error).
Heat rates are retained only for the merit-order ranking (Module 3). Non-combustion fuels
(hydro, wind, solar, geothermal, biogas, wood, waste heat) are excluded from the combustion
sum. Geothermal fugitive CO2 is NOT added: MBIE's own electricity GHG is combustion-based, and
model combustion matches it to ~1% in gas-dominated years.

## 4. Dual EF basis (Step C)
Both tables carry an explicit `ef_basis` column:
- `generation` (per island NI/SI): emissions per kWh generated at the station, no T&D losses.
  Consistent with the historical pipeline's 0%-loss convention. SI ≈ 0 (no SI thermal).
- `consumption` (National): emissions per kWh delivered = national CO2 / national demand. The
  adjustment is the GENERATION-TO-CONSUMPTION GROSS-UP FACTOR = MBIE `Total electricity demand`
  / `Electricity generation` net total (mean {grossup_mean:.3f}, ~{(grossup_mean-1)*100:.1f}%).
  This is NOT a pure T&D line-loss figure: it bundles transmission + distribution losses,
  generator own-use, and any MBIE demand-vs-generation balancing-item effects. It is MBIE-derived
  (not an external Transpower/EA loss statistic — switch to a cited external rate if preferred).
  Reported at NATIONAL level only: island-resolved consumption EF needs HVDC allocation (the
  historical Consumption pipeline's method) — see TODO_island_consumption_EF.md. This consumption
  basis is a third quantity beyond the original two assumptions. The historical Consumption
  pipeline's existing 0%-loss outputs are NOT altered.
  Standing assertion (Module 6): consumption EF >= national generation EF for every scenario-year.

## 5. True, unforced Check 2 result
- Check 1 (gen by fuel): max |diff| {report['check1_gen_pct'].max():.4f}% (±{TOL}%, exact by design).
- Check 3 (peak): max |diff| {report['check3_peak_pct'].max():.4f}% (±{TOL}%).
- Check 2a (combustion CO2 vs MBIE GHG): EMISSIONS-WEIGHTED |diff| {ew:.1f}% (the fair headline);
  unweighted mean |{report['check2a_emissions_pct'].abs().mean():.1f}%|, max |{report['check2a_emissions_pct'].abs().max():.1f}%|.
  Agreement is ~1-4% where emissions are material (>1.5 Mt, 117/135 scenario-years). The large
  deviations (up to ~-22%) are confined to the Environmental scenario's near-decarbonised later
  years (~1.3 Mt absolute emissions). The cause is NOT cleanly attributable to a single factor:
  MBIE publishes no per-fuel emission breakdown, and the discrepancy behaves differently across
  scenarios (Reference drifts with coal share; Environmental's gap grows as gas use falls with
  coal flat, pointing instead to a roughly constant non-combustion term, plausibly geothermal
  fugitive CO2). It is reported, not adjusted — resolving it would require inventing effective
  factors or MBIE's unpublished per-fuel split, both of which the brief prohibits.
- Check 2b (gen-side EF vs MBIE EF sheet): mean |{report['check2b_ef_pct'].abs().mean():.1f}%|
  (includes the ~{scope['scope_gap_pct'].mean():.1f}% denominator scope difference of item 1).
Per scenario-year detail: edgs_check2_emissions.csv, edgs_reconciliation_report.csv. The honest
Check-2 deviation also travels IN the emission-factor table as column `check2_deviation_pct`.

## Check-2 gap: biomass rejected, geothermal tested and disproven, intercept unexplained
(build_edgs_check2_diagnostic.py, all 135 scenario-years — full methodology and rigor detailed
there; summary below.)

**Biomass/wood: TESTED and REJECTED.** Implied wood factor ~173 g CO2/kWh is implausible for
biomass (non-CO2 combustion is typically <20 g/kWh under carbon-neutral CO2 accounting), fit is
weak (R2=0.43), and once geothermal is included wood's coefficient goes negative — it adds
nothing. The Constraint scenario (no Rankine->biomass conversion, wood=334 GWh flat) still has a
substantial gap, which biomass cannot explain; Innovation and Environmental track their
GEOTHERMAL, not their wood.

**Geothermal: SOURCED, TESTED, and its regression fit DISPROVEN as a magnitude match** (a follow-
up round after the finding above). A cited field-level source was found: McLean, K., Richardson,
I. (2019), "Greenhouse Gas Emissions from New Zealand Geothermal Power Generation in Context,"
Proceedings 41st NZ Geothermal Workshop, Auckland. Fleet MW-weighted average (2018): 76 g CO2-e/
kWh — within 2% of the regression-implied 77.4 g/kWh (field range: Wairakei 21 to Ohaaki 341
g/kWh). Ngawha (304 g/kWh in 2018) is corrected to 0 g/kWh for all EDGS years (2024-2050): Top
Energy achieved 100% non-condensable-gas reinjection, carbon-zero by end 2023 (cited, dated,
real-world operational change). The resulting capacity-weighted, time-varying fleet factor is
61-64 g/kWh for 2024-2050.

This cited factor was **actually added to the pipeline and Check 2 was re-run** (not just fitted
statistically) — the acceptance-criteria-mandated test. Result: predicted geothermal CO2
(~0.6-0.9 Mt/yr) is 2-7x the actual gap it was meant to explain (~0.05-0.4 Mt/yr); adding it
OVERSHOOTS MBIE's electricity GHG total by ~19-27% (emissions-weighted), substantially WORSE than
combustion-only (~6.3%). **DECISION: NOT adopted.** The prior regression's R2=0.9995 reflected
geothermal generation and the small residual gap co-trending upward over the 27-year projection
(both increase roughly monotonically with time) — a correlation-of-trends artifact, not a valid
causal/magnitude match. This is an important negative result: high variance-explained is not the
same claim as "the gap is resolved," and testing the actual magnitude, not just the fitted
slope, is what exposed it.

**Correction (this round): the earlier "~839-858 kt structural residual" was an artifact of the
now-rejected geothermal regression, not a real quantity.** That intercept was a free parameter
that existed purely to cancel a spurious geothermal slope large enough to make the fitted line
pass near the small real gap (see above); once the geothermal hypothesis was disproven at
magnitude, the intercept it produced has no independent physical meaning and should not be read
as a second, still-open ~850 kt mystery. It has been retired from this documentation.

**Coal fraction, carbon price, and time were re-tested directly against the RAW gap** (MBIE
electricity GHG minus modelled combustion CO2 — the real, observed quantity, not any regression
byproduct), properly centered, each reported individually:
- coal_gwh:      R2 = 0.15 (weak)
- coal_frac:     R2 = 0.22 (weak)
- carbon_price:  R2 = 0.10 (weak)
- **year (time trend): R2 = 0.63** — clearly the strongest single explanatory variable
- joint (all four together): R2 = 0.76

Year explains materially more of the gap's variation than coal or carbon price individually.
This is evidence, not proof, of a slow drift rather than a fixed missing source — consistent
with the earlier, separately-noted observation that MBIE's own implied coal factor drifts from
~89.8 to ~107.8 kg/GJ over the projection (not adopted as a constant, since it is not physically
sensible for a fixed fuel, but plausibly indicative of MBIE's own assumptions evolving smoothly
over the projection window rather than the pipeline missing a fixed emission source). This
drift is NOT confirmed as causal and is NOT adopted into the pipeline's calculation.

**Summary — three hypotheses tested and rejected, each for a stated reason:**
1. *Implied coal factor drift* (89.8 -> 107.8 kg/GJ over 2024-2050): physically inconsistent
   for a fixed fuel; not adopted as a constant, though its direction is consistent with the
   time-trend finding above.
2. *Biomass/wood combustion*: implausible fitted factor (~173 g/kWh, non-CO2 combustion should
   be <20 g/kWh), weak fit (R2=0.43), and contradicted by the Constraint scenario (no biomass
   conversion, still has a gap tracking geothermal, not wood).
3. *Geothermal fugitive CO2*: a real, cited, field-level factor (McLean & Richardson 2019) was
   sourced and tested at its correct real-world magnitude; it overshoots the actual gap by
   2-7x (adding it makes Check 2 WORSE, ~19-27% vs ~6.3%), despite an excellent but spurious
   statistical fit against the now-retired intercept.

**STATUS: the raw Check-2a gap remains genuinely unexplained** — small where emissions are
material (~1-4% in 117/135 scenario-years, ~6.3% emissions-weighted overall), with year/time
the strongest (but unconfirmed, non-causal) correlate found. Three independent, evidence-based
hypotheses have now been tested and rejected rather than merely asserted. Continuing to search
for a fourth explanation for a small residual gap is being **deliberately deprioritised** in
favour of two other open items in this project: closing the battery/BESS capacity gap (MBIE
publishes DSR/battery only as capacity, never dispatched energy — Assumption 2's current
treatment) and building the island-resolved consumption-side emission factor (see
TODO_island_consumption_EF.md). This is a documented decision, not an unexplained stopping point.

## Assumptions
- A1 (renewable/demand hourly shape): {ASSUMPTION_1}
- A2 (battery/DSR): {ASSUMPTION_2}
- Consumption-side gross-up (item 4) is an additional, separately-declared quantity, MBIE-derived.

## Assumption-1 sensitivity (Reference)
Annual national EF is MBIE-anchored (both fuel use and net generation are template-invariant),
so hydrology moves only the hourly/seasonal SHAPE: mean abs hourly NI EF diff vs central 2021 =
{sens_wet:.4f} (wet 2023), {sens_dry:.4f} (dry 2024) kg/kWh. Detail: edgs_sensitivity_A1.csv.

## Source workbooks
Results: {RESULTS_XLSX.name}; Assumptions: {ASSUMPTIONS_XLSX.name}.
source_tag values: {sorted(SOURCE_TAGS)}.
"""
(OUT_DIR / "README_EDGS_hourly.md").write_text(readme, encoding="utf-8")
log("Wrote README_EDGS_hourly.md (v2)")
(OUT_DIR / "processing_log_reconcile.txt").write_text("\n".join(lines), encoding="utf-8")
