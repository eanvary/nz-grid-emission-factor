"""
Adds geothermal (24-48% of NI generation) to the uncertainty band. IPCC Ch.2 does not
cover geothermal-fluid emissions, so the source is station data from McLean, K. &
Richardson, I. (2019), "Greenhouse Gas Emissions
From Geothermal Power Stations: Context and Opportunities", New Zealand Geothermal
Association -- 12 real NZ geothermal stations, 2018, MW and gCO2eq/kWh each (archived at
../validation_references/McLean_NZGA_GeothermalGHG.pdf). This script:

1. Recomputes the MW-weighted mean from their own per-station table as a cross-check
   (must reproduce their own published "76" before the derived std is trusted).
2. Computes the MW-weighted relative std across the 12 stations -- same cross-sectional
   fleet-spread method already used for GAS (build_fleet_uncertainty.py), applied here to
   an external field study instead of this project's own single-value plant register.
3. Adds GEO to REL_SIGMA and re-runs the full propagation (monthly, annual, hourly),
   alongside (not replacing) the existing GAS-only fleet-adjusted run.
4. Separately, as its own distinct, non-conflated observation, reports the geothermal EFs
   in this project's plant register as the pipeline loads it
   (generation_pipeline/fuel_attribution.py, FuelAttribution().reg). The raw register
   gives every geothermal POC one flat value (99.996 kg/MWh, identical
   HeatRate/EmissionsFactor for all registered POCs), ~24% above McLean &
   Richardson's MW-weighted mean (76 gCO2/kWh). The module's register copy carries the
   per-station correction (geothermal_ef_correction.py), and the pipeline's factors come
   from the NZGA station intensities (FuelAttribution().nzga), so the observation prints
   the corrected per-POC values and the NZGA fleet average. This is separate from the
   EDGS projection pipeline's decision not to use this source as a Check-2 gap-filler
   (a different pipeline and a different use of the data).
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import FuelAttribution  # noqa: E402

# Verbatim from McLean & Richardson (2019), page 2 table (12 NZ geothermal stations, 2018).
GEOTHERMAL_STATIONS = [
    ("Wairakei A&B and binary", 116, 21),
    ("Te Mihi", 157, 43),
    ("Poihipi", 46, 38),
    ("Ohaaki", 31, 341),
    ("Te Huka", 22, 45),
    ("Rotokawa", 33, 84),
    ("Nga Awa Purua (NAP)", 141, 63),
    ("Mokai", 56, 52),
    ("Ngatamariki", 90, 64),
    ("Kawerau (KGL)", 104, 123),
    ("TOPP1", 21, 60),
    ("Ngawha", 23, 304),
]
geo_df = pd.DataFrame(GEOTHERMAL_STATIONS, columns=["station", "mw", "ef_gco2_kwh"])
total_mw = geo_df.mw.sum()
geo_w_mean_gco2 = (geo_df.mw * geo_df.ef_gco2_kwh).sum() / total_mw
geo_w_var = (geo_df.mw * (geo_df.ef_gco2_kwh - geo_w_mean_gco2) ** 2).sum() / total_mw
geo_w_std_gco2 = math.sqrt(geo_w_var)
geo_rel_sigma = geo_w_std_gco2 / geo_w_mean_gco2

print("=== Step 1: reproduce McLean & Richardson's own published weighted average (cross-check) ===")
print(f"  Computed: {geo_w_mean_gco2:.2f} gCO2/kWh   |   Published: 76 gCO2/kWh   |   "
      f"{'MATCH' if abs(geo_w_mean_gco2-76)<0.5 else 'MISMATCH -- STOP, do not trust further'}")
print(f"\n=== Step 2: MW-weighted relative uncertainty across the real 12-station fleet ===")
print(f"  weighted std = {geo_w_std_gco2:.2f} gCO2/kWh, relative sigma = {geo_rel_sigma*100:.2f}%")
print(f"  (driven by two outlier fields: Ohaaki 341, Ngawha 304 gCO2/kWh -- vs. Wairakei's 21)")

geo_df.to_csv(HERE / "geothermal_mclean_richardson_stations.csv", index=False)

fa = FuelAttribution()
geo_pocs = fa.reg[fa.reg["FuelCode"] == "GEO"]
distinct_ef = geo_pocs["EF_kg_per_MWh"].dropna().unique()
print(f"\n=== Separate observation: this project's OWN geothermal point-EF assumption ===")
print(f"  {geo_pocs['PointOfConnectionCode'].nunique()} distinct POCs registered, "
      f"{len(distinct_ef)} distinct EF value(s) in the pipeline's register copy: {sorted(distinct_ef)}")
flat_val = float(distinct_ef[0]) if len(distinct_ef) == 1 else None
if flat_val:
    diff_pct = (flat_val - geo_w_mean_gco2) / geo_w_mean_gco2 * 100
    print(f"  This project uses ONE flat value ({flat_val:.3f} kg/MWh = {flat_val:.1f} gCO2/kWh) "
          f"for every geothermal POC.")
    print(f"  McLean & Richardson's real MW-weighted mean: {geo_w_mean_gco2:.2f} gCO2/kWh.")
    print(f"  Difference: this project's flat value is {diff_pct:+.1f}% vs. the real weighted mean.")
    print(f"  (Observation only -- not a change to the shipped pipeline. See report for scope.)")
else:
    print(f"  Per-POC values (geothermal_ef_correction.py), not one flat value: "
          f"{min(distinct_ef):.1f}-{max(distinct_ef):.1f} kg/MWh.")
if fa.nzga:
    nz = {y: v for (st, y), v in fa.nzga.items() if st == "NZGA MW-weighted average"}
    print(f"  Shipped factors use NZGA station intensities; NZGA MW-weighted average by year (g/kWh): "
          + ", ".join(f"{y}: {v:.1f}" for y, v in sorted(nz.items())))

# Re-run propagation, monthly + hourly, with GEO included in REL_SIGMA.
IPCC_TABLE_2_2 = {
    "CLG": (96100.0, 92800.0, 100000.0), "GAS": (56100.0, 54300.0, 58300.0),
    "DSL": (74100.0, 72600.0, 74800.0), "WOOD": (112000.0, 95000.0, 132000.0),
}
def rel_half_width(d, lo, hi):
    return (abs(d - lo) / d + abs(hi - d) / d) / 2.0
REL_SIGMA_BASE = {f: rel_half_width(*v) for f, v in IPCC_TABLE_2_2.items()}

fleet = pd.read_csv(HERE / "fleet_uncertainty_by_fuel.csv").set_index("fuel_std")["rel_sigma_adopted"].to_dict()
REL_SIGMA_FULL = dict(REL_SIGMA_BASE)
REL_SIGMA_FULL["GAS"] = fleet["GAS"]          # rel_sigma_adopted: sqrt(IPCC Table 2.2 carbon^2 + D3 heat-rate RMS^2); not the fleet dispersion (0.0674 pooled, 0.1615 unit-level), which would double-count known unit differences
_geo_sig = pd.read_csv(HERE / "geo_uncertainty_sigma.csv").set_index("fuel_std")["rel_sigma"]  # build_geo_uncertainty_inputs.py
# geothermal by proxy-rule step: GEO (step 1, NIR 2026 Table 3.2.3, 7.07%), GEO_S2_<station> (step 2,
# sqrt(7.07%^2 + station year-to-year variation^2)), GEO_PROXY (steps 3-4, McLean & Richardson spread 93.97%)
REL_SIGMA_FULL.update({k: float(v) for k, v in _geo_sig.items()})

print("\nFinal REL_SIGMA used for full-coverage run:")
for f, v in REL_SIGMA_FULL.items():
    print(f"  {f}: {v*100:.2f}%")

ZERO_EF_FUELS = {"HYD", "WIN", "SOL"}


def propagate_monthly(fuel_mix_path, rel_sigma):
    df = pd.read_csv(fuel_mix_path)
    rows = []
    for (island, year, month), g in df.groupby(["island", "year", "month"]):
        total_gen = g["gen_mwh"].sum()
        if total_gen <= 0:
            continue
        ef_col = "weighted_ef_kg_per_MWh"
        g = g.copy()
        g[ef_col] = pd.to_numeric(g[ef_col], errors="coerce").fillna(0.0)
        point_ef = (g["gen_mwh"] * g[ef_col]).sum() / total_gen
        var = 0.0
        quantified_gen = 0.0
        for _, r in g.iterrows():
            code = r["fuel_code"]
            w = r["gen_mwh"] / total_gen
            if code in ZERO_EF_FUELS:
                quantified_gen += r["gen_mwh"]
                continue
            if code not in rel_sigma:
                continue
            sigma_i = r[ef_col] * rel_sigma[code]
            var += (w * sigma_i) ** 2
            quantified_gen += r["gen_mwh"]
        rows.append({"island": island, "year": year, "month": month,
                      "point_ef_kg_per_mwh": point_ef, "sigma_kg_per_mwh": math.sqrt(var),
                      "quantified_coverage_pct": quantified_gen / total_gen * 100.0,
                      "total_gen_mwh": total_gen})
    out = pd.DataFrame(rows)
    out["ci95_pct_of_point"] = np.where(
        out["point_ef_kg_per_mwh"] > 0, 1.96 * out["sigma_kg_per_mwh"] / out["point_ef_kg_per_mwh"] * 100.0, np.nan
    )
    return out


monthly_path = HERE / "monthly_fuel_mix_uncertainty.csv"  # GEO split into GEO / GEO_PROXY (build_geo_uncertainty_inputs.py)
print("\nRunning monthly propagation, full coverage (GAS fleet-adjusted + GEO added)...")
monthly_full = propagate_monthly(monthly_path, REL_SIGMA_FULL)
monthly_full.to_csv(HERE / "ipcc_uncertainty_by_island_month_full_coverage.csv", index=False)

ni_full = monthly_full[monthly_full.island == "NI"]
print(f"NI monthly CI% -- full coverage: min={ni_full.ci95_pct_of_point.min():.2f}% "
      f"max={ni_full.ci95_pct_of_point.max():.2f}% mean={ni_full.ci95_pct_of_point.mean():.2f}%")
print(f"NI monthly coverage% -- full: min={ni_full.quantified_coverage_pct.min():.1f}% "
      f"max={ni_full.quantified_coverage_pct.max():.1f}%")

# Annual roll-up
annual_rows = []
for (island, year), g in monthly_full.groupby(["island", "year"]):
    total_gen = g["total_gen_mwh"].sum()
    point_ef = (g["point_ef_kg_per_mwh"] * g["total_gen_mwh"]).sum() / total_gen
    var = ((g["sigma_kg_per_mwh"] * g["total_gen_mwh"] / total_gen) ** 2).sum()
    sigma = math.sqrt(var)
    cov = (g["quantified_coverage_pct"] * g["total_gen_mwh"]).sum() / total_gen
    annual_rows.append({"island": island, "year": year, "point_ef_kg_per_mwh": point_ef,
                         "sigma_kg_per_mwh": sigma,
                         "ci95_pct_of_point": 1.96 * sigma / point_ef * 100.0 if point_ef > 0 else np.nan,
                         "quantified_coverage_pct": cov})
annual_full = pd.DataFrame(annual_rows)
annual_full.to_csv(HERE / "ipcc_uncertainty_by_island_year_full_coverage.csv", index=False)
ni_annual_full = annual_full[annual_full.island == "NI"]
print(f"\nNI annual CI% -- full coverage: min={ni_annual_full.ci95_pct_of_point.min():.2f}% "
      f"max={ni_annual_full.ci95_pct_of_point.max():.2f}%")
print(f"NI annual coverage% -- full: min={ni_annual_full.quantified_coverage_pct.min():.1f}% "
      f"max={ni_annual_full.quantified_coverage_pct.max():.1f}%")

# Hourly (vectorised)
hourly_path = HERE / "hourly_fuel_mix_uncertainty.csv"  # GEO split into GEO / GEO_PROXY
if hourly_path.exists():
    print("\nRunning hourly propagation, full coverage (vectorised)...")
    hdf = pd.read_csv(hourly_path)
    hdf["rel_sigma"] = hdf["fuel_std"].map(REL_SIGMA_FULL).fillna(0.0)
    hdf["is_quantified_combustion"] = hdf["fuel_std"].isin(REL_SIGMA_FULL.keys())
    hdf["is_zero_ef"] = hdf["fuel_std"].isin(ZERO_EF_FUELS)
    hdf["sigma_i"] = hdf["ef_kg_per_mwh"] * hdf["rel_sigma"]

    total_gen = hdf.groupby(["island", "date", "hour"], sort=False)["gen_mwh"].sum()
    weighted_co2 = (hdf["gen_mwh"] * hdf["ef_kg_per_mwh"]).groupby(
        [hdf["island"], hdf["date"], hdf["hour"]]
    ).sum()
    point_ef = weighted_co2 / total_gen

    dq = hdf[hdf["is_quantified_combustion"]].copy()
    tg = total_gen.rename("total_gen_mwh").reset_index()
    dq = dq.merge(tg, on=["island", "date", "hour"], how="left")
    dq["w"] = dq["gen_mwh"] / dq["total_gen_mwh"]
    dq["contrib"] = (dq["w"] * dq["sigma_i"]) ** 2
    var_by_group = dq.groupby(["island", "date", "hour"], sort=False)["contrib"].sum()

    quantified_gen = hdf[hdf["is_quantified_combustion"] | hdf["is_zero_ef"]].groupby(
        ["island", "date", "hour"], sort=False
    )["gen_mwh"].sum()

    out = pd.DataFrame({"total_gen_mwh": total_gen, "point_ef_kg_per_mwh": point_ef})
    out["sigma_kg_per_mwh"] = var_by_group.reindex(out.index).fillna(0.0).apply(math.sqrt)
    out["quantified_coverage_pct"] = (quantified_gen.reindex(out.index).fillna(0.0) / out["total_gen_mwh"] * 100.0)
    out = out.reset_index()
    out["ci95_pct_of_point"] = np.where(
        out["point_ef_kg_per_mwh"] > 0, 1.96 * out["sigma_kg_per_mwh"] / out["point_ef_kg_per_mwh"] * 100.0, np.nan,
    )
    out.to_csv(HERE / "ipcc_uncertainty_by_island_hour_full_coverage.csv", index=False)

    ni_h_full = out[(out.island == "NI") & (out.point_ef_kg_per_mwh > 0)]
    print(f"NI hourly CI% -- full coverage: min={ni_h_full.ci95_pct_of_point.min():.2f}% "
          f"max={ni_h_full.ci95_pct_of_point.max():.2f}% mean={ni_h_full.ci95_pct_of_point.mean():.2f}%")
    print(f"NI hourly coverage% -- full: min={ni_h_full.quantified_coverage_pct.min():.1f}% "
          f"max={ni_h_full.quantified_coverage_pct.max():.1f}%")
    print(f"Wrote ipcc_uncertainty_by_island_hour_full_coverage.csv ({len(out):,} rows)")
else:
    print("\nSkipping hourly: hourly_fuel_mix_NI_SI.csv not found.")
