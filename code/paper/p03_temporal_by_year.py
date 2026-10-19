"""
Paper 03: temporal error of the annual NI factor year by year, per demand profile and trajectory
(primary projection, generation basis). temporal_pct = (annual island mean - load-weighted hourly)
/ load-weighted hourly x 100; positive = the annual mean overstates that year's carbon.
Usage: python p03_temporal_by_year.py <copy_root> <out_dir>
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]); OUT = Path(sys.argv[2]); T = ROOT / "analysis_paper" / "tables"
ef = pd.read_parquet(ROOT / "output" / "edgs" / "edgs_hourly_emission_factor.parquet", filters=[("island", "==", "NI"), ("ef_basis", "==", "generation")])
ef["year"] = ef.datetime_hour.dt.year; ef["dow"] = ef.datetime_hour.dt.dayofweek; ef["hour"] = ef.datetime_hour.dt.hour
sh = pd.read_csv(T / "phase3_load_shapes_stylised.csv")
isl = pd.read_csv(T / "phase3_annual_island_ef.csv"); isl = isl[isl.island == "NI"]
rows = []
for lab in sh.label.unique():
    s = sh[sh.label == lab][["dow", "hour", "raw_intensity"]]
    a = ef.merge(s, on=["dow", "hour"]).groupby(["scenario", "year"]).apply(
        lambda g: np.average(g.emission_factor_kg_co2e_per_kwh, weights=g.raw_intensity), include_groups=False).rename("a").reset_index()
    m = a.merge(isl, on=["scenario", "year"]); m["load_shape"] = lab
    m["temporal_pct"] = 100 * (m.annual_island_ef - m.a) / m.a
    rows.append(m)
out = pd.concat(rows)[["load_shape", "scenario", "year", "a", "annual_island_ef", "temporal_pct"]]
out.to_csv(OUT / "temporal_error_by_year.csv", index=False)
print(out[out.year.isin([2025, 2050])].pivot_table(index=["load_shape", "year"], columns="scenario", values="temporal_pct").round(1).to_string())
