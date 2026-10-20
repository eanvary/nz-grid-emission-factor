"""
EDGS projection, primary variant at hourly resolution: consistent scope, grid-injection basis.

Built alongside the combustion-only (MBIE-reproducing) hourly parquet from build_edgs_dispatch.py,
which is not changed. Inputs:
  output/edgs/edgs_hourly_generation.parquet            hourly generation by island and fuel
                                                         (central template, all scenarios)
  output/edgs/consistent_scope/annual_components_consistent_scope.csv
                                                         annual consistent-scope emissions by
                                                         component and the annual grid share,
                                                         written by build_edgs_consistent_scope.py
Method, per scenario and year:
  - Coal, natural gas, diesel, wood: the annual component (MBIE fuel input x MfE 2025 factor;
    coal already less the Glenbrook-class 7.63 PJ x 91.99 kt; wood CH4+N2O) is spread over hours
    in proportion to that fuel's hourly generation. So Glenbrook-class coal is removed hourly in
    proportion to hourly coal generation.
  - Geothermal: hourly geothermal generation by plant x that plant's intensity for the year. Plant
    generation is the annual capacity share of the island's geothermal (build_edgs_consistent_scope.py),
    so this equals hourly geothermal generation x the year's generation-weighted plant intensity,
    i.e. the annual Geothermal_kt spread in proportion to hourly geothermal generation.
  - Denominator: hourly generation x the year's grid share (grid GWh / total GWh; the same share on
    each island, an estimate, as in annual_ef_by_variant.csv).
All thermal and geothermal plant is North Island, so South Island emissions are zero.
Annual sums reproduce annual_ef_by_variant.csv (variant consistent_scope, EF_*_grid); checked below.
Output: output/edgs/edgs_hourly_emission_factor_primary.parquet
  scenario, island (NI, SI, National), datetime_hour, emissions_kg, generation_mwh,
  grid_generation_mwh, ef_grid_kg_co2e_per_kwh, ef_total_kg_co2e_per_kwh, grid_share
Needs pyarrow (Anaconda interpreter).
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EDGS = ROOT / "output" / "edgs"
CS = EDGS / "consistent_scope"
COMPONENTS = ["Coal", "Natural gas", "Diesel", "Wood", "Geothermal"]

comp = pd.read_csv(CS / "annual_components_consistent_scope.csv")
annual = pd.read_csv(CS / "annual_ef_by_variant.csv")
annual = annual[annual.variant == "consistent_scope"].set_index(["scenario", "year"])

parts = []
for scen in sorted(comp.scenario.unique()):
    g = pd.read_parquet(EDGS / "edgs_hourly_generation.parquet", filters=[("scenario", "==", scen)],
                        columns=["datetime_hour", "island", "fuel_commodity", "generation_mwh"])
    g["year"] = g.datetime_hour.dt.year
    g = g[g.year >= 2024]
    c = comp[comp.scenario == scen].set_index("year")
    em = pd.Series(0.0, index=pd.MultiIndex.from_frame(g[["island", "datetime_hour"]].drop_duplicates()))
    for fuel in COMPONENTS:
        f = g[g.fuel_commodity == fuel]
        kt = f.year.map(c[f"{fuel}_kt"])
        tot = f.groupby("year").generation_mwh.transform("sum")
        missing = sorted(set(c.index[c[f"{fuel}_kt"].abs() > 1e-9]) - set(f.loc[f.generation_mwh > 0, "year"]))
        if missing:
            raise RuntimeError(f"{scen} {fuel}: emissions but no hourly generation in {missing}")
        e = (kt * 1e6 * f.generation_mwh / tot.where(tot > 0, np.nan)).fillna(0.0)  # kg
        em = em.add(pd.Series(e.to_numpy(), index=pd.MultiIndex.from_frame(f[["island", "datetime_hour"]])).groupby(level=[0, 1]).sum(),
                    fill_value=0.0)
    gen = g.groupby(["island", "datetime_hour"]).generation_mwh.sum()
    h = pd.DataFrame({"emissions_kg": em.reindex(gen.index, fill_value=0.0), "generation_mwh": gen}).reset_index()
    nat = h.groupby("datetime_hour", as_index=False)[["emissions_kg", "generation_mwh"]].sum().assign(island="National")
    h = pd.concat([h, nat], ignore_index=True)
    h["grid_share"] = h.datetime_hour.dt.year.map(c["grid_share"])
    h["grid_generation_mwh"] = h.generation_mwh * h.grid_share
    h["ef_grid_kg_co2e_per_kwh"] = np.where(h.grid_generation_mwh > 0, h.emissions_kg / (h.grid_generation_mwh * 1000.0), np.nan)
    h["ef_total_kg_co2e_per_kwh"] = np.where(h.generation_mwh > 0, h.emissions_kg / (h.generation_mwh * 1000.0), np.nan)
    h["scenario"] = scen
    parts.append(h)
out = pd.concat(parts, ignore_index=True)[["scenario", "island", "datetime_hour", "emissions_kg", "generation_mwh",
                                           "grid_generation_mwh", "ef_grid_kg_co2e_per_kwh", "ef_total_kg_co2e_per_kwh", "grid_share"]]
out.to_parquet(EDGS / "edgs_hourly_emission_factor_primary.parquet", index=False)

# check: annual aggregates reproduce annual_ef_by_variant.csv (consistent_scope)
a = out.assign(year=out.datetime_hour.dt.year).groupby(["scenario", "year", "island"])[
    ["emissions_kg", "grid_generation_mwh", "generation_mwh"]].sum()
worst = {}
for (s, y), r in annual.iterrows():
    ni, nat = a.loc[(s, y, "NI")], a.loc[(s, y, "National")]
    worst.setdefault("NI_kt", []).append(abs(ni.emissions_kg / 1e6 - r.NI_kt))
    worst.setdefault("EF_NI_grid", []).append(abs(ni.emissions_kg / ni.grid_generation_mwh - r.EF_NI_grid))
    worst.setdefault("EF_National_grid", []).append(abs(nat.emissions_kg / nat.grid_generation_mwh - r.EF_National_grid))
    worst.setdefault("EF_National", []).append(abs(nat.emissions_kg / nat.generation_mwh - r.EF_National))
print(f"Wrote edgs_hourly_emission_factor_primary.parquet: {len(out):,} rows")
for k, v in worst.items():
    print(f"  max |hourly annual aggregate - annual_ef_by_variant| {k}: {max(v):.3e}")
