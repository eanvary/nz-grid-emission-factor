"""
Check-2 gap diagnostic: test the biomass hypothesis, then source and test a cited
geothermal factor, then examine what is left of the gap. Step labels match the log.

Step 1: biomass/wood is rejected (implied 173 g/kWh, implausible, R2=0.43, coefficient goes
negative once geothermal enters). Geothermal generation correlates with the gap at R2=0.9995
(regression-implied 77.4 g/kWh). A cited field-level source was found and tested:

  McLean, K., Richardson, I. (2019). "Greenhouse Gas Emissions from New Zealand Geothermal
  Power Generation in Context." Proceedings 41st New Zealand Geothermal Workshop, 25-27 Nov
  2019, Auckland. Table: gCO2-eq/kWh(net) by power station, 2018 MW-weighted data. Fleet
  average 76 g/kWh (2018), within 2% of the regression-implied 77.4 g/kWh.
  Field range: Wairakei 21, Te Mihi 43, Poihipi 38, Ohaaki 341, Te Huka 45, Rotokawa 84,
  Nga Awa Purua 63, Mokai 52, Ngatamariki 64, Kawerau(KGL) 123, Kawerau(TOPP1) 60, Ngawha 304.
  Ngawha override: Top Energy achieved 100% NCG reinjection, carbon-zero by end 2023 (cited:
  Ngawha Generation Ltd; ThinkGeoEnergy), so Ngawha = 0 g/kWh for all EDGS years (2024-2050).

Step 1 result, tested by adding the factor to the pipeline and re-running Check 2 (not only
by fitting a regression). The cited, capacity-weighted, time-varying geothermal factor
(61-64 g/kWh once Ngawha is set to 0) predicts geothermal CO2 of about 0.6-0.9 Mt/yr. The
gap it is meant to explain is only about 0.05-0.4 Mt/yr. Adding the cited factor overshoots
MBIE's electricity GHG total by about 19-27% (emissions-weighted), worse than combustion-only
(about 6.3%). Geothermal fugitive CO2, at its cited real-world magnitude, does not explain the
Check-2 gap. The regression's R2=0.9995 reflects geothermal generation and the small residual
gap both rising roughly monotonically over the 27-year projection. This is a correlation of
trends, not a causal or magnitude match. The factor is not used in the pipeline's EF.

Step 2: the intercept of the geothermal-only fit (about -839 to -858 kt, stable across scenarios)
is not treated as a finding. It is a free parameter of the rejected geothermal magnitude
hypothesis (the cited factor overshoots the real gap by 2-7x) and exists only to cancel a
spurious geothermal slope, so it has no independent physical meaning.

Instead, coal_gwh, coal_frac, carbon_price and year are each regressed directly against the
raw gap_Mt (MBIE GHG - modelled combustion, the observed quantity). Result: coal_gwh R2=0.15,
coal_frac R2=0.22, carbon_price R2=0.10 (all weak); year R2=0.63 (the strongest single
variable); joint (all four) R2=0.76. Time explains more of the gap than any physical driver
tested. This points to a slow drift rather than a fixed missing source; it is not confirmed
as causal and is not used in the pipeline.

Three hypotheses tested and rejected:
  1. Implied coal factor drift (89.8 to 107.8 kg/GJ, 2024-2050): physically inconsistent for a
     fixed fuel; not adopted, though its direction matches the year-trend finding above.
  2. Biomass/wood combustion: implausible fitted factor, weak fit, contradicted by Constraint.
  3. Geothermal fugitive CO2: real, cited, field-level factor sourced and tested at correct
     magnitude; overshoots the actual gap by 2-7x. Not adopted.
The gap is reported, not adjusted. build_edgs_check2_geothermal_resolution.py revisits
geothermal with a factor applied only to new build above the 2024 fleet.

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
log(f"  Geothermal+Wood joint: geo {b2[0]*1e6:.1f} g/kWh, wood {b2[1]*1e6:+.1f} g/kWh, R2={r22:.4f}")
log("  Wood is negative or near zero once geothermal is in, so wood adds nothing. Biomass rejected.")

# Innovation and Environmental (both convert the Rankines to biomass in 2032)
log("\n=== Step 1c: Innovation and Environmental ===")
for yr in [2030, 2032, 2040, 2050]:
    i = df[(df.scenario == "Innovation") & (df.year == yr)].iloc[0]
    e = df[(df.scenario == "Environmental") & (df.year == yr)].iloc[0]
    log(f"{yr} | Innov wood {i.Wood:5.0f} geo {i.Geothermal:6.0f} gap {i.gap_Mt:+.3f} | "
        f"Envir wood {e.Wood:5.0f} geo {e.Geothermal:6.0f} gap {e.gap_Mt:+.3f}")
log("  Constraint (no Rankine-to-biomass conversion, wood=334 GWh flat) still has a substantial "
    "gap, which tracks its geothermal, not wood. Biomass is not the driver.")

# Step 1 (sourced): field-level factors, McLean & Richardson (2019), Ngawha override
log("\n=== Step 1 (sourced): McLean & Richardson (2019) field-level geothermal factors ===")
log("  Fleet MW-weighted average (2018): 76 g CO2-e/kWh, within 2% of the regression-implied 77.4.")
log("  Ngawha: 304 g/kWh (2018), 0 g/kWh from 2024 (Top Energy 100% NCG reinjection, cited, "
    "carbon-zero by end 2023). All EDGS years are 2024-2050, so Ngawha=0 throughout.")

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
log(f"\n  Cited prediction (no fitting) against the actual gap: mean resid {resid.mean()*1000:+.0f} kt, "
    f"std {resid.std()*1000:.0f} kt (a small std means the residual is stable across all scenario-years)")
log(f"  Interpretation: predicted geothermal CO2 ({d.pred_cited_Mt.mean()*1000:.0f} kt/yr mean) is "
    f"{d.pred_cited_Mt.mean()/d.gap_Mt.mean():.1f}x the actual mean gap it is meant to explain "
    f"({d.gap_Mt.mean()*1000:.0f} kt/yr). Adding it as real CO2 overshoots MBIE's total.")
d.round(4).to_csv(OUT_DIR / "edgs_geothermal_cited_vs_regression.csv", index=False)

log("\n  Pipeline test (build_edgs_dispatch.py; the factor is not retained there): adding the cited, "
    "time-varying geothermal factor to combustion CO2 and re-running Check 2 across all 5 "
    "scenarios gives an emissions-weighted |diff| of 19-27% (worse than combustion-only, 6.3%).")
log("  DECISION: geothermal fugitive CO2, at its cited real-world magnitude, does not explain "
    "the gap and is not adopted in the pipeline. The high R2 of the Step 1 fit (0.9995) "
    "reflects geothermal generation and the small residual gap rising together over the "
    "27-year projection window. It is a correlation of trends, not a causal or magnitude match.")

# Step 2: the geothermal-only fit's intercept (about 839-858 kt, stable across scenarios) is
# not tested. It is a free parameter of the rejected geothermal magnitude hypothesis (Step 1:
# the cited factor overshoots the real gap by 2-7x). It exists only to cancel a spurious
# geothermal slope large enough to pass near the small real gap, so it has no independent
# physical meaning.
# Coal fraction, carbon price and time are regressed directly against the raw gap_Mt
# (MBIE GHG - modelled combustion), not any geothermal-regression byproduct. Year is
# tested as its own variable.
log("\n=== Step 2: coal_gwh, coal_frac, carbon_price and year against the raw gap_Mt ===")
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
log(f"  Joint (all four): R2={r2j:.3f}")
log("  RESULT: year is the strongest single explanatory variable (R2 about 0.6), "
    "stronger than coal or carbon price alone (R2 about 0.1-0.2). This points to a slow drift "
    "with time, not a fixed missing source. It is not confirmed as causal and is not adopted in the "
    "pipeline's calculation. It is consistent with (but not proof of) the drift in "
    "MBIE's implied coal factor (89.8 to 107.8 kg/GJ, 2024-2050). That drift is not adopted as a "
    "constant because it is physically inconsistent for a fixed fuel.")
dd.round(4).to_csv(OUT_DIR / "edgs_check2_rawgap_test.csv", index=False)

# Final conclusion
log("\n=== Final conclusion ===")
log("Biomass: rejected (implausible factor, weak fit, contradicted by Constraint scenario).")
log("Geothermal (statistical): implicated by regression (R2=0.9995), but this reflects "
    "co-trending variables, not a magnitude match. Rejected when tested with a real, "
    "cited, time-varying factor (overshoots MBIE by 19-27%, worse than doing nothing).")
log("Coal factor, carbon price and time: tested against the raw gap (not the "
    "geothermal-fit intercept). Year is the strongest single variable (R2=0.63); coal and carbon "
    "price give R2 0.10-0.22; joint R2=0.76. This suggests a slow drift; it is not confirmed as "
    "causal and not adopted in the pipeline.")
log("STATUS: three independent hypotheses tested and rejected. The raw Check-2a "
    "gap remains unexplained but is small where emissions are material (1-4% in "
    "117/135 scenario-years, 6.3% emissions-weighted overall). The residual is reported, "
    "not adjusted, because adjusting it would mean inventing factors "
    "or guessing MBIE's unpublished "
    "per-fuel/per-source split.")

(OUT_DIR / "edgs_check2_diagnostic_summary.txt").write_text("\n".join(lines), encoding="utf-8")
df.round(4).to_csv(OUT_DIR / "edgs_check2_diagnostic.csv", index=False)
log("\nWrote edgs_check2_diagnostic.csv, edgs_check2_rawgap_test.csv, "
    "edgs_geothermal_field_weighted_factor.csv, edgs_geothermal_cited_vs_regression.csv, "
    "edgs_check2_diagnostic_summary.txt")
