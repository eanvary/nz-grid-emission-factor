"""
Check-2 gap diagnostic (v2, follow-up brief): test the biomass hypothesis, then source and
test a cited geothermal factor, then investigate the leftover intercept.

STEP 1: biomass/wood REJECTED (implied ~173 g/kWh, implausible, R2=0.43, coefficient goes
negative once geothermal enters). Geothermal generation correlates with the gap at R2=0.9995
(regression-implied 77.4 g/kWh). A CITED field-level source was found and tested:

  McLean, K., Richardson, I. (2019). "Greenhouse Gas Emissions from New Zealand Geothermal
  Power Generation in Context." Proceedings 41st New Zealand Geothermal Workshop, 25-27 Nov
  2019, Auckland. Table: gCO2-eq/kWh(net) by power station, 2018 MW-weighted data. Fleet
  average 76 g/kWh (2018) -- within 2% of the regression-implied 77.4 g/kWh.
  Field range: Wairakei 21, Te Mihi 43, Poihipi 38, Ohaaki 341, Te Huka 45, Rotokawa 84,
  Nga Awa Purua 63, Mokai 52, Ngatamariki 64, Kawerau(KGL) 123, Kawerau(TOPP1) 60, Ngawha 304.
  Ngawha override: Top Energy achieved 100% NCG reinjection, carbon-zero by end 2023 (cited:
  Ngawha Generation Ltd; ThinkGeoEnergy) -- Ngawha = 0 g/kWh for all EDGS years (2024-2050).

STEP 1 RESULT (decisive, tested by actually adding it to the pipeline and re-running Check 2,
not just fitting a regression): the cited, capacity-weighted, time-varying geothermal factor
(~61-64 g/kWh once Ngawha is corrected to 0) predicts geothermal CO2 of ~0.6-0.9 Mt/yr -- but
the ACTUAL gap it is meant to explain is only ~0.05-0.4 Mt/yr. Adding the cited factor OVERSHOOTS
MBIE's electricity GHG total by ~19-27% (emissions-weighted), substantially WORSE than
combustion-only (~6.3%). CONCLUSION: geothermal fugitive CO2, at its real-world cited magnitude,
is NOT the explanation for the Check-2 gap. The earlier regression's R2=0.9995 reflected
geothermal generation and the small residual gap co-trending upward over the 27-year projection
(both increase roughly monotonically with time) -- a correlation-of-trends artifact, not a valid
causal/magnitude match. NOT adopted in the shipped pipeline (reverted after testing).

STEP 2 (CORRECTED, this round): a prior version of this script tested the geothermal-fit's
INTERCEPT (~-839 to -858 kt, stable across scenarios) against coal/carbon-price and reported it
as an "unexplained structural residual." That intercept was a free parameter of the now-REJECTED
geothermal magnitude hypothesis (Step 1: adding the cited factor overshoots the real gap by
2-7x) -- it existed only to cancel a spurious geothermal slope, has no independent physical
meaning, and is RETIRED from this documentation (see the superseded block below, kept only as
a labelled artifact, not a finding).

Corrected re-test: coal_gwh, coal_frac, carbon_price, and YEAR (not tested in isolation before)
regressed directly against the RAW gap_Mt (MBIE GHG - modelled combustion, the real observed
quantity). Result: coal_gwh R2=0.15, coal_frac R2=0.22, carbon_price R2=0.10 (all weak) --
YEAR R2=0.63 (clearly the strongest single variable) -- joint (all four) R2=0.76. Time/year
explains materially more of the gap than any physical driver tested. This is evidence of a slow
drift, not a fixed missing source, and is NOT confirmed as causal or adopted into the pipeline.

THREE HYPOTHESES TESTED AND REJECTED (final status of this line of investigation):
  1. Implied coal factor drift (89.8->107.8 kg/GJ, 2024-2050): physically inconsistent for a
     fixed fuel; not adopted, though its direction matches the year-trend finding above.
  2. Biomass/wood combustion: implausible fitted factor, weak fit, contradicted by Constraint.
  3. Geothermal fugitive CO2: real, cited, field-level factor sourced and tested at correct
     magnitude; overshoots the actual gap by 2-7x. Not adopted.
Hypothesis-chasing on this specific residual is DELIBERATELY DEPRIORITISED after this round in
favour of the battery/BESS capacity gap and the island-resolved consumption-side EF (see
TODO_island_consumption_EF.md) -- a documented decision, not an unexplained stopping point.

Outputs: edgs_check2_diagnostic.csv (135 rows), edgs_check2_rawgap_test.csv,
  edgs_geothermal_field_weighted_factor.csv, edgs_geothermal_cited_vs_regression.csv,
  edgs_check2_diagnostic_summary.txt
"""
import numpy as np
import pandas as pd

from edgs_common import (RESULTS_XLSX, ASSUMPTIONS_XLSX, OUT_DIR, YEARS,
                         geothermal_ef_kg_per_mwh, log_factory)

log, lines = log_factory()

# Assemble the 135-row dataset
ti = pd.read_parquet(OUT_DIR / "edgs_thermal_intensity.parquet")  # combustion-only (geothermal not adopted)
comb = ti.groupby(["scenario", "year"])["combustion_co2_kt"].sum().div(1000).rename("model_comb_Mt")
ghg = pd.read_excel(RESULTS_XLSX, sheet_name="Greenhouse gas emissions")
ghg = (ghg[ghg.Emission_Sector == "Electricity generation"]
       .set_index(["Scenario", "TimePeriod"])["Value"].rename_axis(["scenario", "year"]).rename("mbie_ghg_Mt"))
tgt = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
piv = tgt[tgt.metric == "net_generation"].pivot_table(index=["scenario", "year"], columns="commodity",
                                                       values="value", aggfunc="sum")
df = pd.concat([comb, ghg, piv[["Wood", "Waste heat", "Biogas", "Geothermal"]]], axis=1)
df = df.dropna(subset=["model_comb_Mt", "mbie_ghg_Mt"])
df = df[df.index.get_level_values("year").isin(YEARS)].fillna(0.0)
df["gap_Mt"] = df["mbie_ghg_Mt"] - df["model_comb_Mt"]
df = df.reset_index()
log(f"Assembled {len(df)} scenario-years; gap_Mt range {df.gap_Mt.min():+.3f} to {df.gap_Mt.max():+.3f}")

y = df["gap_Mt"].values


def fit(cols):
    X = np.column_stack([df[c].values for c in cols] + [np.ones(len(df))])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    r2 = 1 - ((y - X @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return b, r2


# Step 1a/1b: biomass rejected, geothermal statistically implicated
log("\n=== Step 1a/1b: individual fits, gap_Mt ~ source_GWh + intercept ===")
for c in ["Wood", "Biogas", "Geothermal"]:
    b, r2 = fit([c])
    log(f"  {c:11s}: implied {b[0]*1e6:7.1f} g CO2/kWh | centered R2 = {r2:.4f}")
bg, r2g = fit(["Geothermal"])
b2, r22 = fit(["Geothermal", "Wood"])
log(f"  Geothermal+Wood joint: geo {b2[0]*1e6:.1f} g/kWh, WOOD {b2[1]*1e6:+.1f} g/kWh, R2={r22:.4f}")
log("  -> wood negative/near-zero once geothermal is in: wood adds nothing. BIOMASS REJECTED.")

# Innovation vs Environmental (both convert Rankine->biomass @2032)
log("\n=== Step 1c: Innovation vs Environmental ===")
for yr in [2030, 2032, 2040, 2050]:
    i = df[(df.scenario == "Innovation") & (df.year == yr)].iloc[0]
    e = df[(df.scenario == "Environmental") & (df.year == yr)].iloc[0]
    log(f"{yr} | INNOV wood {i.Wood:5.0f} geo {i.Geothermal:6.0f} gap {i.gap_Mt:+.3f} | "
        f"ENVIR wood {e.Wood:5.0f} geo {e.Geothermal:6.0f} gap {e.gap_Mt:+.3f}")
log("  Constraint (NO Rankine->biomass conversion, wood=334 GWh flat) still has a substantial "
    "gap, tracking its geothermal, not wood -> confirms biomass is not the driver.")

# Step 1 (sourced): field-level factors, McLean & Richardson (2019), Ngawha override
log("\n=== Step 1 (sourced): McLean & Richardson (2019) field-level geothermal factors ===")
log("  Fleet MW-weighted average (2018): 76 g CO2-e/kWh -- within 2% of regression-implied 77.4.")
log("  Ngawha: 304 g/kWh (2018) -> 0 g/kWh from 2024 (Top Energy 100% NCG reinjection, cited, "
    "carbon-zero by end 2023). All EDGS years are 2024-2050 -> Ngawha=0 throughout.")

reg = pd.read_parquet(OUT_DIR / "edgs_plant_register.parquet")
geo = reg[reg.commodity == "Geothermal"].copy()
geo["ef_g_kwh"] = [geothermal_ef_kg_per_mwh(p, yr)[0] for p, yr in zip(geo.plant, geo.year)]
w = (geo.groupby(["scenario", "year"])
     .apply(lambda d: np.average(d.ef_g_kwh, weights=d.capacity_mw) if d.capacity_mw.sum() > 0 else np.nan,
            include_groups=False)
     .rename("field_weighted_g_per_kwh").reset_index())
w.to_csv(OUT_DIR / "edgs_geothermal_field_weighted_factor.csv", index=False)
log(f"  Capacity-weighted fleet factor, 2024-2050 (Ngawha corrected): {w.field_weighted_g_per_kwh.min():.1f} "
    f"to {w.field_weighted_g_per_kwh.max():.1f} g/kWh (much lower than the 76 g/kWh raw 2018 average, "
    f"which still included Ngawha's high pre-reinjection value).")

d = df.merge(w, on=["scenario", "year"])
d["pred_cited_Mt"] = d.Geothermal * 1e6 * d.field_weighted_g_per_kwh / 1e12  # GWh*1e6 kWh * g/kWh /1e12 = Mt
resid = d.gap_Mt - d.pred_cited_Mt
log(f"\n  CITED prediction (no fitting) vs actual gap: mean resid {resid.mean()*1000:+.0f} kt, "
    f"std {resid.std()*1000:.0f} kt (SMALL std = very stable across all scenario-years)")
log(f"  Interpretation: predicted geothermal CO2 ({d.pred_cited_Mt.mean()*1000:.0f} kt/yr mean) is "
    f"{d.pred_cited_Mt.mean()/d.gap_Mt.mean():.1f}x the actual mean gap it's meant to explain "
    f"({d.gap_Mt.mean()*1000:.0f} kt/yr) -- adding it as real CO2 OVERSHOOTS MBIE's total.")
d.round(4).to_csv(OUT_DIR / "edgs_geothermal_cited_vs_regression.csv", index=False)

log("\n  TESTED IN THE PIPELINE (build_edgs_dispatch.py, then reverted): adding the cited, "
    "time-varying geothermal factor to combustion CO2 and re-running Check 2 across all 5 "
    "scenarios gives emissions-weighted |diff| ~19-27% (WORSE than combustion-only ~6.3%).")
log("  DECISION: geothermal fugitive CO2, at its cited real-world magnitude, does NOT explain "
    "the gap and is NOT adopted in the shipped pipeline. The prior high statistical R2 (0.9995) "
    "reflected geothermal generation and the small residual gap co-trending upward over the "
    "27-year projection window -- correlation of trends, not a valid causal/magnitude match.")

# Step 2 (SUPERSEDED: retained only as a documented artifact, not a finding).
# The per-scenario geothermal-only fit's intercept (previously reported as an "~839-858 kt
# stable structural residual") was a free parameter of the now-REJECTED geothermal magnitude
# hypothesis (see Step 1 above: the cited factor overshoots the real gap by 2-7x). The
# intercept existed only to cancel a spurious geothermal slope large enough to pass near the
# small real gap; it has no independent physical meaning and is NOT a second open finding.
# Superseded by the raw-gap re-test directly below.

# Step 2 (corrected re-test): coal fraction, carbon price, AND time, regressed directly
# against the RAW gap_Mt (MBIE GHG - modelled combustion), not any geothermal-regression
# byproduct. Time/year tested as its own explicit variable (was not isolated last round).
log("\n=== Step 2 (corrected): coal_gwh, coal_frac, carbon_price, YEAR vs RAW gap_Mt ===")
cp = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Commodity prices")
cp = cp[cp.Variable == "Effective carbon price"].rename(
    columns={"Scenario": "scenario", "TimePeriod": "year", "Value": "carbon_price"})[["scenario", "year", "carbon_price"]]
coalgen = ti[ti.fuel == "Coal"].groupby(["scenario", "year"])["model_gwh"].sum().rename("coal_gwh")
totgen = ti.groupby(["scenario", "year"])["model_gwh"].sum().rename("total_thermal_gwh")
dd = (df.merge(coalgen.reset_index(), on=["scenario", "year"], how="left")
      .merge(totgen.reset_index(), on=["scenario", "year"], how="left")
      .merge(cp, on=["scenario", "year"], how="left"))
dd["coal_gwh"] = dd.coal_gwh.fillna(0)
dd["coal_frac"] = dd.coal_gwh / dd.total_thermal_gwh.replace(0, np.nan)
dd = dd.dropna(subset=["coal_frac", "carbon_price"])
yy = dd.gap_Mt.values

for var in ["coal_gwh", "coal_frac", "carbon_price", "year"]:
    xi = dd[var].values
    A_ = np.column_stack([xi, np.ones(len(xi))])
    c, *_ = np.linalg.lstsq(A_, yy, rcond=None); p = A_ @ c
    r2 = 1 - ((yy - p) ** 2).sum() / ((yy - yy.mean()) ** 2).sum()
    log(f"  {var:14s}: coef={c[0]:.6f}, intercept={c[1]*1000:.0f}kt, R2={r2:.3f}")

Xj = np.column_stack([dd.coal_gwh, dd.coal_frac, dd.carbon_price, dd.year, np.ones(len(dd))])
bj, *_ = np.linalg.lstsq(Xj, yy, rcond=None)
r2j = 1 - ((yy - Xj @ bj) ** 2).sum() / ((yy - yy.mean()) ** 2).sum()
log(f"  JOINT (all four): R2={r2j:.3f}")
log("  RESULT: year/time is the strongest single explanatory variable (R2~0.6) — clearly "
    "stronger than coal or carbon price alone (R2~0.1-0.2). This is evidence of a slow drift "
    "with time, not a fixed missing source; NOT confirmed as causal, NOT adopted into the "
    "pipeline's calculation. Consistent with (but not proof of) the separately-noted drift in "
    "MBIE's implied coal factor (~89.8 -> 107.8 kg/GJ, 2024-2050), itself not adopted as a "
    "constant since it is physically inconsistent for a fixed fuel.")
dd.round(4).to_csv(OUT_DIR / "edgs_check2_rawgap_test.csv", index=False)

# Final conclusion
log("\n=== FINAL CONCLUSION ===")
log("Biomass: REJECTED (implausible factor, weak fit, contradicted by Constraint scenario).")
log("Geothermal (statistical): implicated by regression (R2=0.9995) but this reflects "
    "co-trending variables, not a valid magnitude match -- DISPROVEN when tested with a real, "
    "cited, time-varying factor (overshoots MBIE by ~19-27%, worse than doing nothing).")
log("Coal factor / carbon price / time: re-tested against the RAW gap (not the retired "
    "geothermal-fit intercept). Year is the strongest single variable (R2=0.63) vs coal/carbon "
    "price (R2 0.10-0.22); joint R2=0.76. Evidence of a slow drift, NOT confirmed as causal, "
    "NOT adopted into the pipeline.")
log("STATUS: three independent, evidence-based hypotheses tested and rejected. The raw Check-2a "
    "gap remains genuinely unexplained but small where emissions are material (~1-4% in "
    "117/135 scenario-years, ~6.3% emissions-weighted overall). Hypothesis-chasing on this "
    "specific residual is deliberately deprioritised from here; reported, not adjusted, "
    "consistent with the brief's prohibition on inventing factors or MBIE's unpublished "
    "per-fuel/per-source split.")

(OUT_DIR / "edgs_check2_diagnostic_summary.txt").write_text("\n".join(lines), encoding="utf-8")
df.round(4).to_csv(OUT_DIR / "edgs_check2_diagnostic.csv", index=False)
log("\nWrote edgs_check2_diagnostic.csv, edgs_check2_rawgap_test.csv, "
    "edgs_geothermal_field_weighted_factor.csv, edgs_geothermal_cited_vs_regression.csv, "
    "edgs_check2_diagnostic_summary.txt")
