"""
Follow-up brief R2 — wire Brief R's efficiency lever into the HOURLY dispatch, not just the
annual national total. Standalone: reads only existing shipped parquets + Brief R's own CSV
output, writes only new CSVs. Does not modify build_edgs_dispatch.py, edgs_common.py,
build_edgs_efficiency_sensitivity.py, or any shipped output parquet.

WHY THIS SCRIPT EXISTS: Brief R rescaled only the annual `combustion_co2_kt` total per
scenario-year-fuel. It could not, by itself, move the hourly "dirty hour" ceiling the user
flagged (worst-case NI generation EF staying ~flat 2024->2050 in Reference/Growth/Constraint,
per README's dirty-hours discussion) because that ceiling is set by the HOURLY hourly emission
factor shape, which Brief R never touched. This script closes that gap: it derives the implicit
hourly `thermal_shape(t)` directly from the shipped generation parquet (exact, no
re-simulation needed - see fidelity note below), then re-distributes Brief R's annual CO2
DELTA across hours using that same shape, exactly mirroring how build_edgs_dispatch.py itself
distributes thermal CO2 (Step B: "CO2 per fuel = MBIE fuel input x MfE factor, distributed over
the same thermal shape").

FIDELITY (same class of exactness as Brief H, not Briefs E-G's counterfactual approximation):
build_edgs_dispatch.py sets fuel_hourly[com] = mbie_gwh(com) * 1000 * thermal_shape(t), using
the SAME thermal_shape array for every thermal fuel (coal/gas/diesel) within a scenario-year
(see its Step B comment). That means, algebraically, thermal_shape(t) can be recovered EXACTLY
from the shipped hourly generation data alone:
    thermal_shape(t) = total_thermal_generation_mwh(t) / total_thermal_annual_generation_mwh
(summed across Coal+Natural gas+Diesel; ratio is identical whichever thermal fuel or their sum
is used, since they all share the one array) - no re-run of the dispatch script needed, and no
new approximation error introduced (unlike Briefs F/G's ~20 MW reconstruction discrepancy).

Baseline hourly CO2(t) is likewise reconstructed EXACTLY from the shipped
edgs_hourly_emission_factor.parquet x total island generation(t) (inverting the pipeline's own
ef = co2/(gen*1000) formula) - not re-simulated.

Method:
  delta_kt(scenario, year) = Brief R's efficient_co2_kt - baseline_co2_kt (already computed,
                              edgs_efficiency_sensitivity_summary.csv; thermal fuels only, Wood
                              excluded exactly as Brief R excluded it)
  new_co2_kg(t) = baseline_co2_kg(t) + thermal_shape(t) x delta_kt(scenario, year) x 1e6
  new_ef(t)     = new_co2_kg(t) / (island_generation_mwh(t) x 1000)      [generation unaffected]

Outputs (output/edgs/):
  edgs_efficiency_hourly_dispatch_summary.csv   per scenario-year: baseline vs efficiency-
                                                 adjusted mean/p99/max NI generation-side EF
"""
import numpy as np
import pandas as pd

from edgs_common import OUT_DIR, SCENARIOS, THERMAL_COMMODITIES, log_factory

log, lines = log_factory()

# ---------------------------------------------------------------------------
# Load: Brief R's annual delta (thermal fuels only, Wood excluded - matches Brief R exactly)
# ---------------------------------------------------------------------------
nat = pd.read_csv(OUT_DIR / "edgs_efficiency_sensitivity_summary.csv")
delta_kt_map = nat.set_index(["scenario", "year"])["co2_delta_kt"].to_dict()  # kt, <=0

# ---------------------------------------------------------------------------
# Load shipped hourly generation (NI only - all thermal capacity is NI, per Module 2/5)
# ---------------------------------------------------------------------------
gen = pd.read_parquet(OUT_DIR / "edgs_hourly_generation.parquet",
                       columns=["scenario", "island", "datetime_hour", "fuel_commodity",
                                "generation_mwh"])
gen_ni = gen[gen["island"] == "NI"].copy()
gen_ni["year"] = gen_ni["datetime_hour"].dt.year
del gen

# Total NI generation per hour (all fuels incl. renewables/DSR) - the EF denominator
ni_total_gen = (gen_ni.groupby(["scenario", "datetime_hour"])["generation_mwh"]
                .sum().rename("ni_gen_mwh").reset_index())

# Total NI thermal generation per hour (Coal+Natural gas+Diesel present in this dataset)
thermal_mask = gen_ni["fuel_commodity"].isin(THERMAL_COMMODITIES)
ni_thermal = (gen_ni[thermal_mask].groupby(["scenario", "datetime_hour", "year"])["generation_mwh"]
              .sum().rename("ni_thermal_mwh").reset_index())

# thermal_shape(t) = hourly thermal MWh / annual thermal MWh, per scenario-year (exact
# recovery of build_edgs_dispatch.py's internal array - see fidelity note above)
annual_thermal = (ni_thermal.groupby(["scenario", "year"])["ni_thermal_mwh"]
                  .sum().rename("annual_thermal_mwh").reset_index())
ni_thermal = ni_thermal.merge(annual_thermal, on=["scenario", "year"], how="left")
ni_thermal["thermal_shape"] = np.where(ni_thermal["annual_thermal_mwh"] > 0,
                                        ni_thermal["ni_thermal_mwh"] / ni_thermal["annual_thermal_mwh"],
                                        0.0)
del gen_ni

# ---------------------------------------------------------------------------
# Load shipped hourly EF (NI, generation basis) -> reconstruct baseline CO2(t) EXACTLY
# ---------------------------------------------------------------------------
ef = pd.read_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet",
                      columns=["scenario", "island", "datetime_hour", "ef_basis",
                               "emission_factor_kg_co2e_per_kwh"])
ef_ni = ef[(ef["island"] == "NI") & (ef["ef_basis"] == "generation")].copy()
del ef

df = ef_ni.merge(ni_total_gen, on=["scenario", "datetime_hour"], how="left")
df = df.merge(ni_thermal[["scenario", "datetime_hour", "year", "thermal_shape"]],
              on=["scenario", "datetime_hour"], how="left")
df["thermal_shape"] = df["thermal_shape"].fillna(0.0)
df["baseline_co2_kg"] = df["emission_factor_kg_co2e_per_kwh"] * df["ni_gen_mwh"] * 1000.0
df["delta_kt"] = [delta_kt_map.get((s, y), 0.0) for s, y in zip(df["scenario"], df["year"])]
df["co2_delta_kg"] = df["thermal_shape"] * df["delta_kt"] * 1e6  # kt -> kg
df["new_co2_kg"] = df["baseline_co2_kg"] + df["co2_delta_kg"]
with np.errstate(divide="ignore", invalid="ignore"):
    df["new_ef_kg_per_kwh"] = np.where(df["ni_gen_mwh"] > 0,
                                        df["new_co2_kg"] / (df["ni_gen_mwh"] * 1000.0), 0.0)

log(f"Reconstructed {len(df):,} NI generation-side hourly rows "
    f"({df['scenario'].nunique()} scenarios x {df['year'].nunique()} years)")

# Sanity check: baseline reconstruction should reproduce the shipped EF exactly (0 delta year)
sanity = df[df["delta_kt"] == 0]
if len(sanity):
    resid = (sanity["new_ef_kg_per_kwh"] - sanity["emission_factor_kg_co2e_per_kwh"]).abs().max()
    log(f"Sanity check (delta_kt==0 rows, should be ~0): max |new_ef - shipped_ef| = {resid:.2e}")

# ---------------------------------------------------------------------------
# Summary: mean / p99 / max, baseline vs efficiency-adjusted, per scenario-year
# ---------------------------------------------------------------------------
rows = []
for (scenario, year), g in df.groupby(["scenario", "year"]):
    base = g["emission_factor_kg_co2e_per_kwh"]
    eff = g["new_ef_kg_per_kwh"]
    rows.append({
        "scenario": scenario, "year": year,
        "baseline_mean": base.mean(), "efficient_mean": eff.mean(),
        "baseline_p99": base.quantile(0.99), "efficient_p99": eff.quantile(0.99),
        "baseline_max": base.max(), "efficient_max": eff.max(),
    })
summ = pd.DataFrame(rows).sort_values(["scenario", "year"])
summ["p99_delta_pct"] = np.where(summ["baseline_p99"] > 0,
                                  (summ["efficient_p99"] / summ["baseline_p99"] - 1) * 100, np.nan)
summ["max_delta_pct"] = np.where(summ["baseline_max"] > 0,
                                  (summ["efficient_max"] / summ["baseline_max"] - 1) * 100, np.nan)
summ.to_csv(OUT_DIR / "edgs_efficiency_hourly_dispatch_summary.csv", index=False)
log(f"Wrote edgs_efficiency_hourly_dispatch_summary.csv ({len(summ):,} scenario-year rows)")

log("\nDirty-hour ceiling (p99 NI generation EF), baseline -> efficiency-adjusted, "
    "selected years:")
for scenario in SCENARIOS:
    s = summ[summ.scenario == scenario].set_index("year")
    parts = []
    for yr in (2024, 2030, 2040, 2050):
        if yr in s.index:
            r = s.loc[yr]
            parts.append(f"{yr}: {r.baseline_p99:.4f}->{r.efficient_p99:.4f} "
                         f"({r.p99_delta_pct:+.2f}%)")
    log(f"  {scenario}: " + " | ".join(parts))

(OUT_DIR / "processing_log_efficiency_hourly_dispatch.txt").write_text("\n".join(lines),
                                                                       encoding="utf-8")
log("\nNOT adopted into the shipped pipeline - standalone sensitivity only (see docstring).")
