"""
Paper 03, database v1.0.1: build the projection inputs the analysis_paper chain reads, on the
primary variant (consistent scope, grid-injection basis; DATABASE_SPEC.md section 3).

Run in a working copy of the database (git archive of ef-database-v1.0.1), never in the live
repository:  python p03_build_primary_inputs.py <copy_root>

Writes, in <copy_root>/output/edgs/ (the combustion-only originals are kept with the suffix
_combustion_only):
  edgs_hourly_emission_factor.parquet          same schema the chain expects:
      ef_basis=generation, island NI/SI  : primary grid-basis factor (emissions / grid generation)
      ef_basis=consumption, island NI/SI : primary consumption basis (below)
      ef_basis=consumption, island National : national grid-basis factor
  edgs_hourly_emission_factor_tmpl{2017,2023,2024}.parquet   generation NI/SI and National,
      same method on each alternative shape template's hourly generation
  edgs_hourly_island_load_primary.parquet      island generation-level load (consumption weights)

Primary emissions per hour follow projection_pipeline/build_edgs_primary_hourly.py exactly: each annual
consistent-scope component (coal less Glenbrook-class coal, gas, diesel, wood, geothermal) is spread
over hours in proportion to that fuel's hourly generation; denominator = generation x grid share.

Consumption basis (primary): the island split of projection_pipeline/build_edgs_island_consumption.py,
Steps 1-3 and 6. Island generation-level load comes from MBIE's island demand share and each island's
template demand shape, renormalised to national generation; transfer = load - generation; emissions
follow the exporting island's generation-side intensity. The denominator is the island's
generation-level load x grid share, so the consumption and generation bases share one national
total. This removes the 7.6-7.9% demand/generation mismatch of the released combustion-only
consumption rows (analysis_paper phase2_wedge_basis_effect_check.csv), which is why no gross-up
correction is applied downstream.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
EDGS = ROOT / "output" / "edgs"
ASSUMPTIONS = ROOT / "edgs_pipeline" / "electricity-demand-generation-scenarios-2024-assumptions.xlsx"
sys.path.insert(0, str(ROOT / "edgs_pipeline"))
from build_edgs_primary_hourly import primary_hourly  # noqa: E402
from edgs_common import map_weights  # noqa: E402


def ef_rows(h):
    """Generation rows (NI, SI) and the National row in the chain's schema."""
    grid = h.generation_mwh * h.grid_share
    isl = h[["scenario", "island", "datetime_hour"]].copy()
    isl["ef_basis"] = "generation"
    # zero-generation hours (30 SI hours) carry zero emissions: factor 0, not NaN
    isl["emission_factor_kg_co2e_per_kwh"] = np.where(grid > 0, h.emissions_kg / (grid * 1000.0), 0.0)
    nat = h.groupby(["scenario", "datetime_hour"], as_index=False).agg(e=("emissions_kg", "sum"), g=("generation_mwh", "sum"),
                                                                      s=("grid_share", "first"))
    natr = nat[["scenario", "datetime_hour"]].copy()
    natr["island"] = "National"; natr["ef_basis"] = "consumption"
    natr["emission_factor_kg_co2e_per_kwh"] = nat.e / (nat.g * nat.s * 1000.0)
    out = pd.concat([isl, natr[isl.columns]], ignore_index=True)
    out["reconciliation_flag"] = "PRIMARY"
    return out


def consumption_rows(h):
    dem = pd.read_parquet(EDGS / "edgs_shape_demand.parquet")
    dem = dem[dem.template_year == 2021]
    w_ni_base = dem[dem.island == "NI"][["month", "day", "hour", "weight"]]
    w_si_base = dem[dem.island == "SI"][["month", "day", "hour", "weight"]]
    isd = pd.read_excel(ASSUMPTIONS, sheet_name="Island share of demand")
    isd = isd[isd["Variable"] == "North Island share of national demand"]
    ni_share_map = isd.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()
    rows, loads, wcache = [], [], {}
    h = h.assign(year=h.datetime_hour.dt.year)
    for (scen, year), g in h.groupby(["scenario", "year"]):
        idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
        cal = pd.DataFrame({"datetime_hour": idx, "month": idx.month, "day": idx.day, "hour": idx.hour})
        if year not in wcache:
            wcache[year] = (map_weights(cal, w_ni_base, template_year=2021), map_weights(cal, w_si_base, template_year=2021))
        w_ni, w_si = wcache[year]
        ni_share = float(ni_share_map.get((scen, year), 0.61))
        p = g.pivot_table(index="datetime_hour", columns="island", values=["emissions_kg", "generation_mwh"], aggfunc="sum").reindex(idx, fill_value=0.0)
        gNI, gSI = p[("generation_mwh", "NI")].to_numpy(), p[("generation_mwh", "SI")].to_numpy()
        eNI, eSI = p[("emissions_kg", "NI")].to_numpy(), p[("emissions_kg", "SI")].to_numpy()
        share = float(g.grid_share.iloc[0]); nat = gNI + gSI
        rNI, rSI = ni_share * w_ni, (1 - ni_share) * w_si; ssum = rNI + rSI
        no = ssum <= 0
        rNI = np.where(no, ni_share, rNI); rSI = np.where(no, 1 - ni_share, rSI); ssum = rNI + rSI
        lNI, lSI = nat * rNI / ssum, nat * rSI / ssum
        tNI = lNI - gNI
        impNI, expNI = np.clip(tNI, 0, None), np.clip(-tNI, 0, None)
        impSI, expSI = expNI, impNI
        with np.errstate(divide="ignore", invalid="ignore"):
            iNI = np.where(gNI > 0, eNI / gNI, 0.0); iSI = np.where(gSI > 0, eSI / gSI, 0.0)   # kg per MWh generated
        cNI = (gNI - expNI) * iNI + impNI * iSI
        cSI = (gSI - expSI) * iSI + impSI * iNI
        assert abs((cNI + cSI).sum() - (eNI + eSI).sum()) <= 1e-6 * max(1.0, (eNI + eSI).sum()), (scen, year)
        for isl, c_, l_ in (("NI", cNI, lNI), ("SI", cSI, lSI)):
            with np.errstate(divide="ignore", invalid="ignore"):
                ef = np.where(l_ > 0, c_ / (l_ * share * 1000.0), 0.0)
            rows.append(pd.DataFrame({"scenario": scen, "island": isl, "datetime_hour": idx, "ef_basis": "consumption",
                                      "emission_factor_kg_co2e_per_kwh": ef, "reconciliation_flag": "PRIMARY"}))
            loads.append(pd.DataFrame({"scenario": scen, "island": isl, "datetime_hour": idx, "load_mwh": l_}))
    return pd.concat(rows, ignore_index=True), pd.concat(loads, ignore_index=True)


if __name__ == "__main__":
    for f in ["edgs_hourly_emission_factor", "edgs_hourly_emission_factor_tmpl2017",
              "edgs_hourly_emission_factor_tmpl2023", "edgs_hourly_emission_factor_tmpl2024"]:
        src, keep = EDGS / f"{f}.parquet", EDGS / f"{f}_combustion_only.parquet"
        if src.exists() and not keep.exists():
            src.rename(keep)
    h = primary_hourly(EDGS, "edgs_hourly_generation.parquet")
    ef = ef_rows(h)
    cons, load = consumption_rows(h)
    out = pd.concat([ef, cons], ignore_index=True)
    out.to_parquet(EDGS / "edgs_hourly_emission_factor.parquet", index=False)
    load.to_parquet(EDGS / "edgs_hourly_island_load_primary.parquet", index=False)
    # check against the database's own primary hourly file
    ref = pd.read_parquet(EDGS / "edgs_hourly_emission_factor_primary.parquet", columns=["scenario", "island", "datetime_hour", "ef_grid_kg_co2e_per_kwh"])
    m = ef[ef.ef_basis == "generation"].merge(ref, on=["scenario", "island", "datetime_hour"])
    d = (m.emission_factor_kg_co2e_per_kwh - m.ef_grid_kg_co2e_per_kwh.fillna(0.0)).abs().max()
    print(f"central: {len(out):,} rows; max |diff| against edgs_hourly_emission_factor_primary.parquet = {d:.2e} kg/kWh")
    print(out.groupby(["island", "ef_basis"]).emission_factor_kg_co2e_per_kwh.agg(["size", "mean", "max"]).to_string())
    for ty in (2017, 2023, 2024):
        ht = primary_hourly(EDGS, f"edgs_hourly_generation_tmpl{ty}.parquet")
        ef_rows(ht).to_parquet(EDGS / f"edgs_hourly_emission_factor_tmpl{ty}.parquet", index=False)
        print(f"template {ty}: written")
