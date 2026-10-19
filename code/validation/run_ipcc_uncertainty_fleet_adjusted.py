"""
Re-runs the monthly and hourly IPCC Approach-1 propagation with GAS's relative
uncertainty replaced by the adopted value from build_fleet_uncertainty.py (since 2026-09-29
per-unit factor uncertainty, sqrt(IPCC Table 2.2 carbon^2 + D3 heat-rate RMS^2) = 4.06%;
previously the fleet dispersion, 6.74%; IPCC Table 2.2 default 3.56%) -- CLG, DSL, WOOD unchanged (single-plant
or unregistered fleets gave a degenerate/unavailable fleet estimate, so they keep the
IPCC default, per build_fleet_uncertainty.py's own printed verdict).

This does NOT overwrite the original IPCC-default results
(ipcc_uncertainty_by_island_{month,year,hour,day}.csv) -- both are kept side by side,
matching this project's own established convention (see edgs_pipeline's Brief-series
corrections) of never silently replacing a prior figure.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent

fleet = pd.read_csv(HERE / "fleet_uncertainty_by_fuel.csv").set_index("fuel_std")["rel_sigma_adopted"].to_dict()

# Exact IPCC Table 2.2 relative half-widths -- recomputed from the same
# (default, lower, upper) triplets as run_ipcc_uncertainty_quantification.py,
# not hand-copied rounded constants, so the "original" baseline below is a
# byte-identical reproduction of the earlier report's figures.
IPCC_TABLE_2_2 = {
    "CLG": (96100.0, 92800.0, 100000.0),
    "GAS": (56100.0, 54300.0, 58300.0),
    "DSL": (74100.0, 72600.0, 74800.0),
    "WOOD": (112000.0, 95000.0, 132000.0),
}


def rel_half_width(default, lower, upper):
    return (abs(default - lower) / default + abs(upper - default) / default) / 2.0


REL_SIGMA_ORIGINAL = {f: rel_half_width(*v) for f, v in IPCC_TABLE_2_2.items()}
REL_SIGMA_FLEET_ADJUSTED = dict(REL_SIGMA_ORIGINAL)
REL_SIGMA_FLEET_ADJUSTED["GAS"] = fleet["GAS"]  # rel_sigma_adopted: per-unit carbon + heat-rate uncertainty (build_fleet_uncertainty.py)

print("Relative sigma used, original vs. fleet-adjusted:")
for f in REL_SIGMA_ORIGINAL:
    tag = " <- CHANGED" if REL_SIGMA_FLEET_ADJUSTED[f] != REL_SIGMA_ORIGINAL[f] else ""
    print(f"  {f}: {REL_SIGMA_ORIGINAL[f]:.4f} -> {REL_SIGMA_FLEET_ADJUSTED[f]:.4f}{tag}")

ZERO_EF_FUELS = {"HYD", "WIN", "SOL"}
EXCLUDED_FUELS = {"GEO", "ELE"}


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
        for _, r in g.iterrows():
            code = r["fuel_code"]
            w = r["gen_mwh"] / total_gen
            if code not in rel_sigma:
                continue
            sigma_i = r[ef_col] * rel_sigma[code]
            var += (w * sigma_i) ** 2
        rows.append({"island": island, "year": year, "month": month,
                      "point_ef_kg_per_mwh": point_ef, "sigma_kg_per_mwh": math.sqrt(var),
                      "total_gen_mwh": total_gen})
    out = pd.DataFrame(rows)
    out["ci95_pct_of_point"] = np.where(
        out["point_ef_kg_per_mwh"] > 0, 1.96 * out["sigma_kg_per_mwh"] / out["point_ef_kg_per_mwh"] * 100.0, np.nan
    )
    return out


ROOT = HERE.parent.parent
monthly_path = ROOT / "output" / "monthly_fuel_mix_NI_SI.csv"

print("\nRunning monthly propagation, original IPCC defaults...")
monthly_orig = propagate_monthly(monthly_path, REL_SIGMA_ORIGINAL)
print("Running monthly propagation, fleet-adjusted GAS...")
monthly_fleet = propagate_monthly(monthly_path, REL_SIGMA_FLEET_ADJUSTED)

monthly_fleet.to_csv(HERE / "ipcc_uncertainty_by_island_month_fleet_adjusted.csv", index=False)

ni_orig = monthly_orig[monthly_orig.island == "NI"]["ci95_pct_of_point"].dropna()
ni_fleet = monthly_fleet[monthly_fleet.island == "NI"]["ci95_pct_of_point"].dropna()
print(f"\nNI monthly CI% -- original:        min={ni_orig.min():.2f}% max={ni_orig.max():.2f}% mean={ni_orig.mean():.2f}%")
print(f"NI monthly CI% -- fleet-adjusted:  min={ni_fleet.min():.2f}% max={ni_fleet.max():.2f}% mean={ni_fleet.mean():.2f}%")
widen_pct = (ni_fleet.mean() / ni_orig.mean() - 1) * 100
print(f"Mean widening from fleet adjustment: {widen_pct:+.1f}%")

# Annual roll-up (same disclosed simplification as the existing scripts)
monthly_fleet["year"] = monthly_fleet["year"].astype(int)
annual_rows = []
for (island, year), g in monthly_fleet.groupby(["island", "year"]):
    total_gen = g["total_gen_mwh"].sum()
    point_ef = (g["point_ef_kg_per_mwh"] * g["total_gen_mwh"]).sum() / total_gen
    var = ((g["sigma_kg_per_mwh"] * g["total_gen_mwh"] / total_gen) ** 2).sum()
    sigma = math.sqrt(var)
    annual_rows.append({"island": island, "year": year, "point_ef_kg_per_mwh": point_ef,
                         "sigma_kg_per_mwh": sigma, "ci95_pct_of_point": 1.96 * sigma / point_ef * 100.0 if point_ef > 0 else np.nan})
annual_fleet = pd.DataFrame(annual_rows)
annual_fleet.to_csv(HERE / "ipcc_uncertainty_by_island_year_fleet_adjusted.csv", index=False)

ni_annual_orig = pd.read_csv(HERE / "ipcc_uncertainty_by_island_year.csv")
ni_annual_orig = ni_annual_orig[ni_annual_orig.island == "NI"]["ci95_pct_of_point"]
ni_annual_fleet = annual_fleet[annual_fleet.island == "NI"]["ci95_pct_of_point"]
print(f"\nNI annual CI% -- original:       min={ni_annual_orig.min():.2f}% max={ni_annual_orig.max():.2f}%")
print(f"NI annual CI% -- fleet-adjusted: min={ni_annual_fleet.min():.2f}% max={ni_annual_fleet.max():.2f}%")
print(f"\nWrote ipcc_uncertainty_by_island_month_fleet_adjusted.csv and "
      f"ipcc_uncertainty_by_island_year_fleet_adjusted.csv")

# ---------------------------------------------------------------------------
# Hourly (vectorised, mirroring run_ipcc_uncertainty_hourly.py's approach --
# this is the headline resolution now that Finding 4 is closed).
# ---------------------------------------------------------------------------
hourly_path = HERE / "hourly_fuel_mix_NI_SI.csv"
if hourly_path.exists():
    print("\nRunning hourly propagation, both variants (vectorised)...")
    hdf = pd.read_csv(hourly_path)

    def propagate_hourly_vectorised(hdf, rel_sigma):
        hdf = hdf.copy()
        hdf["rel_sigma"] = hdf["fuel_std"].map(rel_sigma).fillna(0.0)
        hdf["is_quantified_combustion"] = hdf["fuel_std"].isin(rel_sigma.keys())
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

        out = pd.DataFrame({"total_gen_mwh": total_gen, "point_ef_kg_per_mwh": point_ef})
        out["sigma_kg_per_mwh"] = var_by_group.reindex(out.index).fillna(0.0).apply(math.sqrt)
        out = out.reset_index()
        out["ci95_pct_of_point"] = np.where(
            out["point_ef_kg_per_mwh"] > 0,
            1.96 * out["sigma_kg_per_mwh"] / out["point_ef_kg_per_mwh"] * 100.0, np.nan,
        )
        return out

    hourly_orig = propagate_hourly_vectorised(hdf, REL_SIGMA_ORIGINAL)
    hourly_fleet = propagate_hourly_vectorised(hdf, REL_SIGMA_FLEET_ADJUSTED)
    hourly_fleet.to_csv(HERE / "ipcc_uncertainty_by_island_hour_fleet_adjusted.csv", index=False)

    ni_h_orig = hourly_orig[(hourly_orig.island == "NI") & (hourly_orig.point_ef_kg_per_mwh > 0)]["ci95_pct_of_point"]
    ni_h_fleet = hourly_fleet[(hourly_fleet.island == "NI") & (hourly_fleet.point_ef_kg_per_mwh > 0)]["ci95_pct_of_point"]
    print(f"NI hourly CI% -- original:       min={ni_h_orig.min():.2f}% max={ni_h_orig.max():.2f}% mean={ni_h_orig.mean():.2f}%")
    print(f"NI hourly CI% -- fleet-adjusted: min={ni_h_fleet.min():.2f}% max={ni_h_fleet.max():.2f}% mean={ni_h_fleet.mean():.2f}%")
    print(f"Wrote ipcc_uncertainty_by_island_hour_fleet_adjusted.csv ({len(hourly_fleet):,} rows)")
else:
    print("\nSkipping hourly fleet-adjusted run: hourly_fuel_mix_NI_SI.csv not found "
          "(run build_hourly_fuel_mix.py first).")
