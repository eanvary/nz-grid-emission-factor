"""
EDGS projection, variant "consistent scope": annual island emission factors built on the same
scope as the metered historical series, alongside the existing "combustion only" series.

  combustion_only    the current projection (build_edgs_dispatch.py): MBIE fuel input x MfE 2024
                     factors (gas 54.0, coal 92.6, diesel 69.4 kg CO2-e/GJ) + wood CH4+N2O. No
                     geothermal. Includes Glenbrook-class coal.
  consistent_scope   MBIE fuel input x MfE 2025 catalogue factors (Table A.2, gross, CO2: gas
                     54.057909, coal 91.99, diesel 69.203964 t/TJ; as the historical series)
                     + wood CH4+N2O (unchanged)
                     - Glenbrook-class coal: 7.63 PJ carries zero emissions (IPPU 2.C.1, as the
                       historical series). ASSUMPTION: this component is inside MBIE's coal input
                       in every scenario and year; it is only isolated directly in Environmental
                       and Innovation from 2032, where coal stays at 7.63 PJ / 577 GWh / ~119 MW
                       after the Rankines convert to biomass. Before 2032 all scenarios run 13.59 PJ.
                     + geothermal: plant generation (MBIE geothermal GWh x capacity share, the
                       pipeline's allocation rule) x plant intensity from
                       geothermal_projection_intensity.csv (existing stations: NZGA CY2024 held
                       flat, with announced reinjection from its sourced year; other plant by the
                       proxy rule: (1) source-specific figure, (2) same station's nearest
                       published year, (3) nearest station on the same field, following that
                       station's time path ('follows'), (4) NZGA fleet average 53 g/kWh).
                       Per plant and year: geothermal_intensity_by_plant_year.csv.
  consistent_new0 / consistent_new76   sensitivities: all new geothermal plant at 0 / 76 g/kWh.

Denominators. EF_NI / EF_National use total generation: annual island totals from
output/edgs/edgs_hourly_generation.parquet, which equal MBIE's total net generation (all
solar, including distributed, and all cogeneration). EF_NI_grid / EF_National_grid use a
grid-injection basis matching the metered series: grid generation = (MBIE electricity
emissions / MBIE grid emission factor, EDGS 2024 Results "Emission factors") x k, where k is the
mean over 2015-2023 of metered generation (output/annual_emission_factor_NI_SI.csv) / that
implied MBIE grid generation (Reference, historical). The same grid share is applied to each
island (ESTIMATE). MBIE's factor is published to four decimals (about +/-0.2% in the implied
denominator). All thermal and
geothermal plant is North Island in the projection register; South Island carries biogas only.
check2: national totals vs MBIE published "Electricity generation" emissions (EDGS 2024 Results),
unforced. Outputs: output/edgs/consistent_scope/. Needs pyarrow (Anaconda interpreter).
"""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "output" / "edgs" / "consistent_scope"
OUT.mkdir(parents=True, exist_ok=True)

MFE2025_T_PER_TJ = {"Natural gas": 54.057909, "Coal": 91.99, "Diesel": 69.203964}
GLENBROOK_COAL_PJ = 7.63
NEW_SENSITIVITIES = {"consistent_new0": 0.0, "consistent_new76": 76.0}

x = pd.ExcelFile(HERE / "EDGS_2024_Results.xlsx")
ghg = x.parse("Greenhouse gas emissions")
mbie_kt = ghg[ghg.Emission_Sector == "Electricity generation"].set_index(["Scenario", "TimePeriod"]).Value * 1000
mbie_ef = x.parse("Emission factors").set_index(["Scenario", "TimePeriod"]).Value  # kg CO2-e/kWh, grid only
mbie_grid_gwh = mbie_kt / mbie_ef  # kt / (kg/kWh) = GWh
met = pd.read_csv(ROOT / "output" / "annual_emission_factor_NI_SI.csv").groupby("year").total_gen_MWh.sum() / 1000.0
K_YEARS = range(2015, 2024)
k_by_year = {y: met[y] / mbie_grid_gwh[("Reference", y)] for y in K_YEARS}
K_GRID = sum(k_by_year.values()) / len(k_by_year)
u = x.parse("Electricity generation")
use = u[u.Variable == "Electricity generation use"].set_index(["Scenario", "TimePeriod", "Commodity"]).Value
geo_gwh = u[(u.Commodity == "Geothermal") & (u.Variable == "Net electricity generation")].set_index(["Scenario", "TimePeriod"]).Value

ti = pd.read_parquet(ROOT / "output" / "edgs" / "edgs_thermal_intensity.parquet")
ti["scenario"] = ti.scenario.astype(str)
comb_now = ti[ti.fuel != "Wood"].groupby(["scenario", "year"]).combustion_co2_kt.sum()
wood = ti[ti.fuel == "Wood"].groupby(["scenario", "year"]).combustion_co2_kt.sum()

gen = pd.read_parquet(ROOT / "output" / "edgs" / "edgs_hourly_generation.parquet", columns=["scenario", "island", "datetime_hour", "generation_mwh"])
gen["scenario"] = gen.scenario.astype(str)
gen["island"] = gen.island.astype(str)
gen["year"] = gen.datetime_hour.dt.year
isl_gwh = gen.groupby(["scenario", "island", "year"]).generation_mwh.sum() / 1000.0

# geothermal plant intensities by year
pi = pd.read_csv(HERE / "geothermal_projection_intensity.csv")
reg = pd.read_parquet(ROOT / "output" / "edgs" / "edgs_plant_register.parquet")
g = reg[(reg.commodity == "Geothermal") & (reg.capacity_mw > 0)].copy()
g["scenario"] = g.scenario.astype(str)
missing = set(g.plant) - set(pi.plant)
if missing:
    raise RuntimeError(f"geothermal_projection_intensity.csv has no row for: {sorted(missing)}")
PI = pi.set_index("plant")


def intensity(plant, year):
    """g/kWh for a plant and year: a 'follows' row takes its reference plant's path (proxy rule
    step 3); otherwise base (or g_per_kwh_measured from measured_year, the step 1 tie-break), a step change from change_year, and an optional linear trend from
    the change-year value to g_per_kwh_trend_end at trend_end_year (flat after)."""
    r = PI.loc[plant]
    if isinstance(r.follows, str) and r.follows:
        return intensity(r.follows, year)
    if pd.isna(r.change_year) or year < r.change_year:
        # a measured period more recent than the base (step 1 tie-break) applies from its year
        if not pd.isna(r.measured_year) and year >= r.measured_year:
            return float(r.g_per_kwh_measured)
        return float(r.g_per_kwh_base)
    if pd.isna(r.trend_end_year):
        return float(r.g_per_kwh_after)
    f = min(1.0, (year - r.change_year) / (r.trend_end_year - r.change_year))
    return float(r.g_per_kwh_after + f * (r.g_per_kwh_trend_end - r.g_per_kwh_after))


g = g.merge(pi[["plant", "rule", "estimate"]], on="plant", how="left")
g["g_per_kwh"] = [intensity(p, y) for p, y in zip(g.plant, g.year)]
pd.DataFrame([{"plant": p, "year": y, "g_per_kwh": intensity(p, y)} for p in PI.index for y in range(2024, 2051)]).to_csv(
    OUT / "geothermal_intensity_by_plant_year.csv", index=False, float_format="%.3f")
g["share"] = g.capacity_mw / g.groupby(["scenario", "year"]).capacity_mw.transform("sum")
g["gwh"] = [geo_gwh.get((s, y), 0.0) * sh for s, y, sh in zip(g.scenario, g.year, g.share)]
g["new"] = g.status != "Current"


def geo_kt(override_new=None):
    gi = g.g_per_kwh if override_new is None else g.g_per_kwh.where(~g.new, override_new)
    return (g.gwh * gi / 1000.0).groupby([g.scenario, g.year]).sum()  # GWh x g/kWh / 1000 = kt


GEO = {"combustion_only": None, "consistent_scope": geo_kt()}
GEO.update({v: geo_kt(nv) for v, nv in NEW_SENSITIVITIES.items()})
rows, comp = [], []
for (s, y), m in mbie_kt.items():
    if y < 2024 or (s, y) not in comb_now.index:
        continue
    comb25 = sum(use.get((s, y, f), 0.0) * fac for f, fac in MFE2025_T_PER_TJ.items())  # PJ x t/TJ = kt
    glen = GLENBROOK_COAL_PJ * MFE2025_T_PER_TJ["Coal"]
    w = wood.get((s, y), 0.0)
    ni, si = isl_gwh.get((s, "NI", y), 0.0), isl_gwh.get((s, "SI", y), 0.0)
    # components of the consistent-scope variant, for the hourly build (build_edgs_primary_hourly.py)
    comp.append({"scenario": s, "year": y,
                 "Coal_kt": use.get((s, y, "Coal"), 0.0) * MFE2025_T_PER_TJ["Coal"] - glen,
                 "Natural gas_kt": use.get((s, y, "Natural gas"), 0.0) * MFE2025_T_PER_TJ["Natural gas"],
                 "Diesel_kt": use.get((s, y, "Diesel"), 0.0) * MFE2025_T_PER_TJ["Diesel"],
                 "Wood_kt": w, "Geothermal_kt": GEO["consistent_scope"].get((s, y), 0.0),
                 "grid_share": mbie_grid_gwh[(s, y)] * K_GRID / (ni + si)})
    for v, geo in GEO.items():
        if geo is None:
            k, gk, gl = comb_now[(s, y)] + w, 0.0, 0.0
        else:
            gk, gl = geo.get((s, y), 0.0), glen
            k = comb25 - gl + w + gk
        # all emissions are North Island in the projection (South Island biogas CH4/N2O is negligible)
        g_grid = mbie_grid_gwh[(s, y)] * K_GRID
        share = g_grid / (ni + si)
        rows.append({"scenario": s, "year": y, "variant": v, "MBIE_kt": m, "NI_kt": k, "NI_GWh": ni, "SI_GWh": si,
                     "EF_NI": k / ni * 1000 if ni else float("nan"), "EF_SI": 0.0, "EF_National": k / (ni + si) * 1000,
                     "grid_GWh": g_grid, "grid_share": share, "NI_grid_GWh": ni * share, "SI_grid_GWh": si * share,
                     "EF_NI_grid": k / (ni * share) * 1000 if ni else float("nan"), "EF_SI_grid": 0.0,
                     "EF_National_grid": k / g_grid * 1000, "grid_basis_estimate": True,
                     "geothermal_kt": gk, "glenbrook_removed_kt": gl})
d = pd.DataFrame(rows)
d.to_csv(OUT / "annual_ef_by_variant.csv", index=False, float_format="%.4f")
pd.DataFrame(comp).to_csv(OUT / "annual_components_consistent_scope.csv", index=False)
summ = []
for v, dv in d.groupby("variant"):
    err = dv.NI_kt - dv.MBIE_kt
    summ.append({"variant": v, "check2_emissions_weighted_abs_dev_pct": err.abs().sum() / dv.MBIE_kt.sum() * 100,
                 "mean_signed_pct": (err / dv.MBIE_kt).mean() * 100,
                 "signed_2024_2030_pct": (err / dv.MBIE_kt)[dv.year <= 2030].mean() * 100,
                 "signed_2040_2050_pct": (err / dv.MBIE_kt)[dv.year >= 2040].mean() * 100})
s = pd.DataFrame(summ)
s.to_csv(OUT / "check2_by_variant.csv", index=False, float_format="%.3f")
(OUT / "NOTES.md").write_text(
    "# Consistent-scope projection variant\n\n"
    "Built by edgs_pipeline/build_edgs_consistent_scope.py. See its docstring for the definitions.\n\n"
    "## Boundary break in MBIE's accounting at 2023/2024\n\n"
    "- MBIE's historical electricity emissions (EDGS 2024 Results, Status Historical, to 2023) include the whole\n"
    "  geothermal fleet: 2015 4.872 Mt vs MBIE quarterly workbook total with geothermal 4.874 Mt (without 4.061).\n"
    "- MBIE's projected totals for 2024-2030 equal combustion from MBIE's own fuel input to within +0.00 to +0.04 Mt\n"
    "  once MBIE's implied gas factor (~51.95 kg/GJ) is used, leaving no room for the ~0.48 Mt of existing geothermal.\n"
    "- MBIE's geothermal heat input steps from 198.8 PJ (2023, historical) to 263.5 PJ (2024, projected) at near-constant\n"
    "  generation (EDGS 2024 Results, 'Electricity generation use', Geothermal).\n"
    "- The consistent-scope variant therefore does not reproduce MBIE's published totals by construction; check2 is\n"
    "  reported unforced for both variants (check2_by_variant.csv).\n\n"
    "## Grid-injection denominator (EF_*_grid)\n\n"
    f"grid GWh = MBIE emissions / MBIE grid emission factor x k, k = {K_GRID:.4f} (mean 2015-2023 of metered\n"
    "generation / implied MBIE grid generation, Reference; by year: "
    + ", ".join(f"{yy} {v:.4f}" for yy, v in k_by_year.items()) + ").\n"
    "The same grid share applies to each island (ESTIMATE). EF_NI / EF_National keep the total-generation denominator.\n\n"
    "## Assumption: Glenbrook-class coal\n\n"
    "7.63 PJ of coal a year carries zero emissions in every scenario and year. It is isolated directly only in\n"
    "Environmental and Innovation from 2032; before 2032 it is assumed to sit inside the 13.59 PJ in all scenarios.\n",
    encoding="utf-8")
pd.set_option("display.width", 220)
print(s.round(2).to_string(index=False))
print("k =", round(K_GRID, 4), {yy: round(v, 4) for yy, v in k_by_year.items()})
