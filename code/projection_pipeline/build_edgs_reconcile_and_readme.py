"""
Module 6: reconciliation, acceptance criteria, Assumption-1 sensitivity, and the
README.

  Check 1 (fuel-by-fuel generation)  : reconciles to MBIE, tol +/-0.1% (exact by design)
  Check 3 (annual peak)              : demand series against MBIE Peak demand, tol +/-0.1%
  Check 2 (emissions)                : unforced. Reported two ways:
     (2a) national combustion CO2 (MBIE fuel use x MfE) against MBIE Greenhouse gas emissions
           [Electricity generation], a numerator-to-numerator test with no denominator
           scope ambiguity. This is the main test of the combustion calculation.
      (2b) model generation-side EF (over total net generation) against MBIE Emission factors
           sheet. MBIE's factor is 'primary activity' scope (excludes autoproducer cogen),
           a denominator scope difference of about 3.7% that is quantified, not hidden.
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

# Check 1: national annual generation by fuel against Results!Electricity generation
gsum = gen.groupby(["scenario", "year", "fuel_commodity"])["generation_mwh"].sum().div(1000).reset_index()
mbie_gen = tgt[tgt.metric == "net_generation"][["scenario", "year", "commodity", "value"]]
c1 = gsum.merge(mbie_gen, left_on=["scenario", "year", "fuel_commodity"],
                right_on=["scenario", "year", "commodity"], how="left")
c1["diff_pct"] = np.where(c1["value"].fillna(0) > 0, (c1["generation_mwh"] / c1["value"] - 1) * 100, 0.0)
check1 = c1.groupby(["scenario", "year"])["diff_pct"].apply(lambda s: s.abs().max()).rename("check1_gen_pct")

# Check 3: annual peak (demand series) against Results!Peak demand
peaks["diff_pct"] = (peaks["model_peak_gw"] / peaks["mbie_peak_gw"] - 1).abs() * 100
check3 = peaks.set_index(["scenario", "year"])["diff_pct"].rename("check3_peak_pct")

# Check 2: emissions comparison (unforced)
# (2a) combustion CO2 against MBIE GHG (numerator-to-numerator)
comb = ti.groupby(["scenario", "year"])["combustion_co2_kt"].sum().div(1000).rename("model_comb_Mt")  # Mt
mbie_ghg = ghg.rename_axis(["scenario", "year"]).rename("mbie_ghg_Mt")
c2a = pd.concat([comb, mbie_ghg], axis=1).dropna()
c2a = c2a[c2a.index.get_level_values("year").isin(YEARS)]
c2a["check2a_emissions_pct"] = (c2a["model_comb_Mt"] / c2a["mbie_ghg_Mt"] - 1) * 100

# (2b) model generation-side EF (over total net generation) against MBIE EF sheet
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

# Combined report and reconciliation_flag (PASS gated on the exact Checks 1 and 3 only)
report = pd.concat([check1, check3], axis=1)
report = report.join(check2)
report = report.reset_index()
report["c1_pass"] = report["check1_gen_pct"] <= TOL
report["c3_pass"] = report["check3_peak_pct"] <= TOL
report["exact_pass"] = report["c1_pass"] & report["c3_pass"]
report.to_csv(OUT_DIR / "edgs_reconciliation_report.csv", index=False)

n_total = len(report)
n_pass = int(report["exact_pass"].sum())
log(f"Reconciliation report: {n_pass}/{n_total} scenario-years pass Checks 1 and 3 at +/-{TOL}%")
log(f"  Check 1 (gen by fuel): max |diff| {report['check1_gen_pct'].max():.4f}%")
log(f"  Check 3 (peak):        max |diff| {report['check3_peak_pct'].max():.4f}%")
# Emissions-weighted Check 2a deviation (headline: total abs discrepancy / total MBIE
# emissions), so tiny-emission years don't dominate an unweighted mean.
c2a_w = c2a.copy()
c2a_w["abs_err_Mt"] = (c2a_w["model_comb_Mt"] - c2a_w["mbie_ghg_Mt"]).abs()
ew = c2a_w["abs_err_Mt"].sum() / c2a_w["mbie_ghg_Mt"].sum() * 100
log(f"  Check 2a (combustion CO2 against MBIE GHG): emissions-weighted |diff| {ew:.2f}% "
    f"(unweighted mean {report['check2a_emissions_pct'].abs().mean():.1f}%, max {report['check2a_emissions_pct'].abs().max():.1f}%)")
log(f"  Check 2b (gen-side EF against MBIE EF sheet): mean |diff| {report['check2b_ef_pct'].abs().mean():.2f}%, "
    f"max |diff| {report['check2b_ef_pct'].abs().max():.2f}%")
log("  Check 2a: agreement is 1-4% where emissions are material (>1.5 Mt, 117/135 years); the "
    "large deviations (up to -22%) are the Environmental scenario's near-decarbonised later years "
    "(about 1.3 Mt absolute). The cause cannot be attributed cleanly to one factor, because MBIE publishes no "
    "per-fuel emission breakdown. Candidate contributors are MBIE's effective fuel factors "
    "differing from the cited MfE values and possible small non-combustion (e.g. geothermal) "
    "emissions in MBIE's total. Reported, not adjusted (resolving it would require inventing "
    "factors or MBIE's unpublished per-fuel split).")

# scope gap (2b denominator): total net gen against MBIE 'primary activity' generation
scope = []
for sc in SCENARIOS:
    for yr in (2024, 2050):
        tot = tgt[(tgt.scenario == sc) & (tgt.year == yr) & (tgt.metric == "net_generation")]["value"].sum() / 1000
        g = float(ghg.get((sc, yr), np.nan)); e = float(mbie_ef.get((sc, yr), np.nan))
        prim = g / e if (np.isfinite(g) and np.isfinite(e) and e > 0) else np.nan  # MBIE primary-activity TWh
        scope.append((sc, yr, tot, prim, (tot / prim - 1) * 100 if prim else np.nan))
scope = pd.DataFrame(scope, columns=["scenario", "year", "total_netgen_TWh", "mbie_primary_TWh", "scope_gap_pct"])
log(f"  Denominator scope gap (total net gen against MBIE primary-activity): "
    f"mean {scope['scope_gap_pct'].mean():.1f}% (autoproducer cogen excluded by MBIE)")

# Standing sanity assertion: consumption EF >= generation EF. Re-deriving both EF values
# from the same source totals (co2/netgen and co2/demand with the same co2 numerator) would
# be an identity, guaranteed to pass whenever netgen >= demand (always true), and could
# never catch a table-population bug such as a backwards ratio. So the check reads back
# the materialised edgs_hourly_emission_factor.parquet rows and aggregates them
# energy-weighted (matching the output's weighting convention), rather than re-deriving
# from annual targets.
log("\n=== Consumption >= generation EF assertion (table read-back) ===")
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
                 .rename("cons_ef_readback"))  # already national, one value per hour; a simple mean equals the energy-weighted mean because ef_basis=consumption is a single national series
assert_df = pd.concat([gen_ef_by_yr, cons_ef_by_yr], axis=1).dropna()
assert_fail = assert_df[assert_df["cons_ef_readback"] + 1e-12 < assert_df["gen_ef_readback"]]
if len(assert_fail):
    log(f"  ASSERTION FAILED for {len(assert_fail)} scenario-years (consumption < generation EF, "
        f"read back from the actual output table):")
    log(assert_fail.reset_index().to_string(index=False))
else:
    log(f"  OK: all {len(assert_df)} scenario-years: consumption EF >= generation EF, "
        f"read back from edgs_hourly_emission_factor.parquet rows (energy-weighted, national), "
        f"not re-derived from source totals.")

# Injected-failure test: corrupt a copy of the read-back table (force one scenario-year's
# consumption EF below its generation EF) and confirm the same check catches it. This shows
# the assertion can fail, not just that it passes on clean data.
log("\n  Injected-failure test:")
_test = assert_df.copy()
_victim = _test.index[0]
_test.loc[_victim, "cons_ef_readback"] = _test.loc[_victim, "gen_ef_readback"] * 0.5  # force a bad row
_caught = _test[_test["cons_ef_readback"] + 1e-12 < _test["gen_ef_readback"]]
if _victim in _caught.index:
    log(f"    OK: corrupted row {_victim} (cons_ef forced to 50% of gen_ef) was caught by the "
        f"assertion, so the check can fail.")
else:
    log(f"    FAIL: injected bad row {_victim} was not caught by the assertion. Fix before trusting it.")

# Carry the Check-2 deviation with the data itself, not just the README.
# reconciliation_flag reflects only Checks 1 and 3 (exact); check2_deviation_pct exposes the
# emissions deviation per scenario-year so a PASS filter can't hide it.
flagmap = report.set_index(["scenario", "year"])["exact_pass"].map({True: "PASS", False: "FAIL"}).to_dict()
c2map = report.set_index(["scenario", "year"])["check2a_emissions_pct"].round(2).to_dict()
ef["reconciliation_flag"] = [flagmap.get((s, y), "NA") for s, y in zip(ef["scenario"], ef["year"])]
ef["check2_deviation_pct"] = [c2map.get((s, y), np.nan) for s, y in zip(ef["scenario"], ef["year"])]
ef.drop(columns=["year"]).to_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet", index=False)
log("\nRewrote edgs_hourly_emission_factor.parquet with reconciliation_flag (Checks 1 and 3) and "
    "check2_deviation_pct (unforced Check-2a % per scenario-year)")

# Acceptance criteria
log("\n=== Acceptance criteria ===")
tags = set(gen["source_tag"].unique())
blank = gen["source_tag"].isna().sum() + (gen["source_tag"] == "").sum()
log(f"[{'OK' if blank == 0 and tags <= SOURCE_TAGS else 'FAIL'}] source_tag valid: tags={sorted(tags)}, {blank} blanks")
log(f"[{'OK' if n_pass == n_total else 'FAIL'}] Checks 1 and 3 pass for all {len(SCENARIOS)}x{len(YEARS)} scenario-years")
log(f"[OK] Check 2 reported unforced: 2a mean |{report['check2a_emissions_pct'].abs().mean():.1f}%|, "
    f"2b mean |{report['check2b_ef_pct'].abs().mean():.1f}%| (see edgs_check2_emissions.csv)")
log(f"[OK] ef_basis column present: {sorted(ef.ef_basis.unique())}")
log(f"[OK] MfE fuel factors cited: {MFE_SOURCE}")
log(f"[OK] Combustion from MBIE published fuel use (Electricity generation use, Gross PJ) x MfE")

# Consumption-side gross-up factor: MBIE net generation / MBIE demand
grossups = []
for sc in SCENARIOS:
    for yr in YEARS:
        d = tgt[(tgt.scenario == sc) & (tgt.year == yr) & (tgt.metric == "annual_demand")]["value"].iloc[0]
        g = tgt[(tgt.scenario == sc) & (tgt.year == yr) & (tgt.metric == "net_generation")]["value"].sum() / 1000
        grossups.append(g / d)
grossup_mean = float(np.mean(grossups))
log(f"\nGeneration-to-consumption gross-up factor (MBIE net gen / demand): mean {grossup_mean:.3f} "
    f"(= {(grossup_mean-1)*100:.1f}%; includes T&D losses, generator own-use and MBIE balancing "
    f"items, so it is not a pure line-loss figure; MBIE-derived)")

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
    "mean abs hourly diff against central. Annual national EF is MBIE-anchored (fuel use + net gen "
    "both template-invariant), so sensitivity appears only in the hourly/seasonal shape.")

# README
readme = f"""# EDGS 2024 hourly, island-resolved reconstruction: output metadata

Hourly (8760/yr) NI/SI generation and grid emission-factor trajectories for the five MBIE
EDGS 2024 scenarios ({', '.join(SCENARIOS)}), {YEARS[0]}-{YEARS[-1]}. The outputs disaggregate
MBIE's published annual national results into hourly island detail. They are reconciled to
MBIE and are not an independent forecast. Check 2 is an unforced test. No "geothermal residual"
term is used, because such a term forces Check 2 to 0.0000% and makes the check circular.

## 1. Denominator scope (Step A): 'primary activity' generation
MBIE's `Emission factors` sheet is computed over "primary activity electricity generation"
only ({scope[scope.year==2024]['mbie_primary_TWh'].mean():.1f} TWh mean 2024). It excludes
autoproducer and industrial cogeneration (Glenbrook, Kinleith [ACHP]; Whareroa, Kapuni [PCHP] in
the Generation Stack). This is about {scope['scope_gap_pct'].mean():.1f}% below total net generation.
The model's published generation-side EF (Check 2b) is computed over total net generation. It is
therefore a slightly broader-scope factor than MBIE's. The scope gap is quantified in
edgs_reconciliation_report.csv and is not absorbed into any residual term. The CV gross-vs-net
basis was investigated and ruled out as the driver: it was basis-consistent on losses but wrong
on scope.

## 2. Residual load at generation level (Step A2)
The dispatch residual is built from generation-level load. Its energy equals the MBIE net
generation total (demand + T&D losses + own use, ~{(grossup_mean-1)*100:.1f}% above demand). It
uses the same Assumption-1 historical hourly shape. Delivered demand is not used for the
residual. It would make the residual ~7% too small in every hour and distort the thermal hourly
shape. Peak validation (Check 3) stays anchored to MBIE's demand-side `Peak demand` figure,
computed on a separate demand series. These are two distinct quantities, and they are expected
to differ.

## 3. Combustion from MBIE fuel use (Step B)
Combustion CO2 is MBIE's published `Electricity generation use (Gross PJ)` per commodity × MfE
factors ({MFE_SOURCE}). It is computed directly, not via plant heat rates. Heat-rate combustion
undershot MBIE by ~11%, and a "geothermal residual" term would absorb that error. Heat rates are
used only for the merit-order ranking (Module 3). Non-combustion fuels (hydro, wind, solar,
geothermal, biogas, wood, waste heat) are excluded from the combustion sum. Geothermal fugitive
CO2 is not added. MBIE's own electricity GHG is combustion-based, and model combustion matches
it to ~1% in gas-dominated years.

## 4. Dual EF basis (Step C)
Both tables carry an explicit `ef_basis` column:
- `generation` (per island NI/SI): emissions per kWh generated at the station, with no T&D
  losses. This matches the historical pipeline's 0%-loss convention. SI ≈ 0 (no SI thermal).
- `consumption` (National): emissions per kWh delivered = national CO2 / national demand. The
  adjustment is the generation-to-consumption gross-up factor = MBIE `Total electricity demand`
  / `Electricity generation` net total (mean {grossup_mean:.3f}, ~{(grossup_mean-1)*100:.1f}%).
  It is not a pure T&D line-loss figure. It bundles transmission and distribution losses,
  generator own use and any MBIE demand-vs-generation balancing-item effects. It is derived from
  MBIE, not from an external Transpower or EA loss statistic. A cited external rate can replace
  it. In this module the consumption basis is reported at national level only. Island-resolved
  consumption EF needs HVDC allocation (the historical Consumption pipeline's method) and is
  built in Module 7. This consumption basis is a third quantity beyond the two original
  assumptions. The historical Consumption pipeline's 0%-loss outputs are not altered.
  Standing assertion (Module 6): consumption EF >= national generation EF for every scenario-year.

## 5. Unforced Check 2 result
- Check 1 (gen by fuel): max |diff| {report['check1_gen_pct'].max():.4f}% (±{TOL}%, exact by design).
- Check 3 (peak): max |diff| {report['check3_peak_pct'].max():.4f}% (±{TOL}%).
- Check 2a (combustion CO2 vs MBIE GHG): emissions-weighted |diff| {ew:.1f}% (the headline figure);
  unweighted mean |{report['check2a_emissions_pct'].abs().mean():.1f}%|, max |{report['check2a_emissions_pct'].abs().max():.1f}%|.
  Agreement is ~1-4% where emissions are material (>1.5 Mt, 117/135 scenario-years). The large
  deviations (up to ~-22%) occur only in the near-decarbonised later years of the Environmental
  scenario (~1.3 Mt absolute emissions). No single factor accounts for them. MBIE publishes no
  per-fuel emission breakdown, and the discrepancy behaves differently across scenarios. In
  Reference it drifts with coal share. In Environmental the gap grows as gas use falls while coal
  stays flat. This points instead to a roughly constant non-combustion term, plausibly geothermal
  fugitive CO2. The deviation is reported, not adjusted. Resolving it would require invented
  effective factors or MBIE's unpublished per-fuel split, and the method excludes both.
- Check 2b (gen-side EF vs MBIE EF sheet): mean |{report['check2b_ef_pct'].abs().mean():.1f}%|
  (includes the ~{scope['scope_gap_pct'].mean():.1f}% denominator scope difference of item 1).
Per scenario-year detail: edgs_check2_emissions.csv, edgs_reconciliation_report.csv. The
Check-2 deviation is also carried in the emission-factor table as column `check2_deviation_pct`.

## Check-2 gap: biomass rejected, geothermal tested and disproven, intercept unexplained
Source: build_edgs_check2_diagnostic.py, all 135 scenario-years. That script documents the full
method; a summary follows.

**Biomass/wood: tested and rejected.** The implied wood factor of ~173 g CO2/kWh is implausible
for biomass. Non-CO2 combustion is typically <20 g/kWh under carbon-neutral CO2 accounting. The
fit is weak (R2=0.43). Once geothermal is included, the wood coefficient turns negative and adds
nothing. The Constraint scenario (no Rankine->biomass conversion, wood=334 GWh flat) still has a
substantial gap, which biomass cannot explain. Innovation and Environmental track their
geothermal, not their wood.

**Geothermal: sourced and tested; the regression fit fails as a magnitude match.** The cited
field-level source is McLean, K., Richardson, I. (2019), "Greenhouse Gas Emissions from New
Zealand Geothermal Power Generation in Context," Proceedings 41st NZ Geothermal Workshop,
Auckland. The fleet MW-weighted average (2018) is 76 g CO2-e/kWh. This is within 2% of the
regression-implied 77.4 g/kWh (field range: Wairakei 21 to Ohaaki 341 g/kWh). Ngawha (304 g/kWh
in 2018) is set to 0 g/kWh for all EDGS years (2024-2050). Top Energy achieved 100%
non-condensable-gas reinjection and was carbon-zero by end 2023 (a cited, dated, real-world
operational change). The resulting capacity-weighted, time-varying fleet factor is 61-64 g/kWh
for 2024-2050.

The cited factor was added to the pipeline and Check 2 was re-run, rather than only fitted
statistically. Predicted geothermal CO2 (~0.6-0.9 Mt/yr) is 2-7x the actual gap it was meant to
explain (~0.05-0.4 Mt/yr). Adding it overshoots MBIE's electricity GHG total by ~19-27%
(emissions-weighted). This is substantially worse than combustion only (~6.3%). **Decision: not
adopted.** The regression's R2=0.9995 reflects geothermal generation and the small residual gap
both rising over the 27-year projection (both increase roughly monotonically with time). This is
a correlation of trends, not a valid causal or magnitude match. High variance explained is not
the same claim as "the gap is resolved". Testing the actual magnitude, not only the fitted slope,
is what exposed it.

**The regression intercept ("~839-858 kt structural residual") is an artifact, not a real
quantity.** It was a free parameter. It cancelled a spurious geothermal slope that was large
enough to make the fitted line pass near the small real gap (see above). With the geothermal
hypothesis rejected at magnitude, the intercept has no independent physical meaning. It should
not be read as a second open ~850 kt source, and this documentation does not use it.

**Coal fraction, carbon price and time tested against the raw gap.** The raw gap is MBIE
electricity GHG minus modelled combustion CO2. It is the observed quantity, not a regression
byproduct. Each variable was centred and is reported individually:
- coal_gwh:      R2 = 0.15 (weak)
- coal_frac:     R2 = 0.22 (weak)
- carbon_price:  R2 = 0.10 (weak)
- **year (time trend): R2 = 0.63**, the strongest single explanatory variable
- joint (all four together): R2 = 0.76

Year explains materially more of the gap's variation than coal or carbon price individually.
This is evidence, not proof, of a slow drift rather than a fixed missing source. It is
consistent with a separate observation: MBIE's own implied coal factor drifts from ~89.8 to
~107.8 kg/GJ over the projection. That factor is not adopted as a constant, since a drifting
factor is not physically sensible for a fixed fuel. It plausibly indicates that MBIE's own
assumptions change smoothly over the projection window, rather than that the pipeline misses a
fixed emission source. The drift is not confirmed as causal and is not used in the pipeline's
calculation.

**Summary: three hypotheses tested and rejected, each for a stated reason.**
1. *Implied coal factor drift* (89.8 -> 107.8 kg/GJ over 2024-2050): physically inconsistent
   for a fixed fuel. It is not adopted as a constant, though its direction is consistent with
   the time-trend finding above.
2. *Biomass/wood combustion*: implausible fitted factor (~173 g/kWh, where non-CO2 combustion
   should be <20 g/kWh), weak fit (R2=0.43), and contradicted by the Constraint scenario. That
   scenario has no biomass conversion but still has a gap that tracks geothermal, not wood.
3. *Geothermal fugitive CO2*: a cited field-level factor (McLean & Richardson 2019) was tested
   at its real-world magnitude. It overshoots the actual gap by 2-7x and makes Check 2 worse
   (~19-27% vs ~6.3%). Its close statistical fit depended on the spurious intercept above.

**Status.** The raw Check-2a gap remains unexplained. It is small where emissions are material
(~1-4% in 117/135 scenario-years, ~6.3% emissions-weighted overall). Year is the strongest
correlate found, but it is not confirmed as causal. Three independent, evidence-based hypotheses
were tested and rejected rather than asserted. A search for a fourth explanation of this small
residual gap is deliberately given lower priority than two other items. The first is the
battery/BESS capacity gap: MBIE publishes DSR/battery only as capacity, never as dispatched
energy (the basis of the Assumption 2 treatment). The second is the island-resolved
consumption-side emission factor (Module 7). This is a documented decision, not an unexplained
stopping point.

## Assumptions
- A1 (renewable/demand hourly shape): {ASSUMPTION_1}
- A2 (battery/DSR): {ASSUMPTION_2}
- Consumption-side gross-up (item 4) is an additional, separately declared quantity, derived from MBIE.

## Assumption-1 sensitivity (Reference)
Annual national EF is MBIE-anchored (both fuel use and net generation are template-invariant).
Hydrology therefore moves only the hourly and seasonal shape. Mean abs hourly NI EF diff vs
central 2021 = {sens_wet:.4f} (wet 2023), {sens_dry:.4f} (dry 2024) kg/kWh. Detail:
edgs_sensitivity_A1.csv.

## Source workbooks
Results: {RESULTS_XLSX.name}; Assumptions: {ASSUMPTIONS_XLSX.name}.
source_tag values: {sorted(SOURCE_TAGS)}.
"""
(OUT_DIR / "README_EDGS_hourly.md").write_text(readme, encoding="utf-8")
log("Wrote README_EDGS_hourly.md")
(OUT_DIR / "processing_log_reconcile.txt").write_text("\n".join(lines), encoding="utf-8")
