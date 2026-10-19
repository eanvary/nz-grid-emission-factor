"""
Paper 03: the two sensitivity cases of Section 3 on the same footing as the main decomposition
(105 cases, six orders of the three steps). North Island building, generation basis.
  templates  the four shape templates (2021 central, 2017, 2023, 2024) with the stylised profiles
  bdg2       six metered office shapes and their mean, central template
Usage: python p03_six_order_sensitivity.py <copy_root> <out_dir>
Writes six_order_sensitivity.csv and adds the key "six_order_sensitivity" to numbers_for_text.json.
"""
import json, sys
from itertools import permutations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve()
EDGS = ROOT / "output" / "edgs"; AP = ROOT / "analysis_paper"
SCEN = ["Reference", "Growth", "Constraint", "Innovation", "Environmental"]
FACTORS = ("temporal", "spatial", "trajectory")
CASES = [(2025, 10, 10), (2025, 25, 25), (2025, 30, 26), (2027, 10, 10), (2027, 25, 24), (2030, 10, 10), (2030, 25, 21)]


def six_orders(V):
    out = {f: [] for f in FACTORS}
    for perm in permutations(range(3)):
        state = [0, 0, 0]; prev = V[(0, 0, 0)]
        for f in perm:
            state[f] = 1; cur = V[tuple(state)]; out[FACTORS[f]].append(cur - prev); prev = cur
    return out


def hourly(suf):
    """NI hourly factor with its generation weight, and the national hourly factor."""
    ef = pd.read_parquet(EDGS / f"edgs_hourly_emission_factor{suf}.parquet")
    ef = ef[(ef.ef_basis == "generation") & ef.island.isin(["NI", "SI"])]
    gen = pd.read_parquet(EDGS / f"edgs_hourly_generation{suf}.parquet", columns=["scenario", "island", "datetime_hour", "generation_mwh"])
    gen = gen.groupby(["scenario", "island", "datetime_hour"], observed=True).generation_mwh.sum().reset_index()
    g = ef.merge(gen, on=["scenario", "island", "datetime_hour"], how="left")
    g["w"] = g.generation_mwh.fillna(0); g["co2"] = g.emission_factor_kg_co2e_per_kwh * g.w
    nat = g.groupby(["scenario", "datetime_hour"], observed=True).agg(co2=("co2", "sum"), w=("w", "sum")).reset_index()
    nat["ef"] = nat.co2 / nat.w
    ni = g[g.island == "NI"].rename(columns={"emission_factor_kg_co2e_per_kwh": "ef"})[["scenario", "datetime_hour", "ef", "w"]]
    for d in (ni, nat):
        t = d.datetime_hour.dt
        d["year"] = t.year; d["month"] = t.month; d["dow"] = t.dayofweek; d["hour"] = t.hour; d["is_weekend"] = d.dow >= 5
    return ni, nat


def wmean(d, col):
    return d.groupby(["scenario", "year"], observed=True).apply(
        lambda x: np.average(x.ef, weights=x[col]) if x[col].sum() > 0 else 0.0, include_groups=False)


def run(ni, nat, shape, keys, wcol, tag, label):
    a_y = wmean(ni.merge(shape, on=keys), wcol); ap_y = wmean(nat.merge(shape, on=keys), wcol)
    isl_y = wmean(ni, "w"); nat_y = wmean(nat, "w")
    rows = []
    for sc in SCEN:
        for sy, L, n in CASES:
            yrs = range(sy, sy + n); S = lambda s: sum(s[(sc, y)] for y in yrs)
            V = {(0, 0, 0): S(a_y), (1, 0, 0): S(isl_y), (0, 1, 0): S(ap_y), (1, 1, 0): S(nat_y),
                 (0, 0, 1): a_y[(sc, sy)] * n, (1, 0, 1): isl_y[(sc, sy)] * n, (0, 1, 1): ap_y[(sc, sy)] * n, (1, 1, 1): nat_y[(sc, sy)] * n}
            so = six_orders(V)
            r = dict(set=tag, load_shape=label, scenario=sc, start_year=sy, period=L, n_years=n, E_a=V[(0, 0, 0)],
                     total=V[(1, 1, 1)] - V[(0, 0, 0)], total_pct=100 * (V[(1, 1, 1)] - V[(0, 0, 0)]) / V[(0, 0, 0)])
            for f in FACTORS:
                r[f] = float(np.mean(so[f])); r[f + "_min"] = min(so[f]); r[f + "_max"] = max(so[f])
            st = [abs(x) / abs(t) if abs(t) > 1e-15 else np.inf for x, t in zip(so["spatial"], so["temporal"])]
            r["orders_spatial_gt_temporal"] = int(sum(x > 1 for x in st)); r["ratio_min_over_orders"] = min(st)
            rows.append(r)
    return rows


rows = []
sty = pd.read_csv(AP / "tables" / "phase3_load_shapes_stylised.csv")
for suf, tag in (("", "template_2021"), ("_tmpl2017", "template_2017"), ("_tmpl2023", "template_2023"), ("_tmpl2024", "template_2024")):
    ni, nat = hourly(suf)
    for lab in sty.label.unique():
        rows += run(ni, nat, sty[sty.label == lab][["dow", "hour", "raw_intensity"]], ["dow", "hour"], "raw_intensity", tag, lab)
    if suf == "":
        bd = pd.read_csv(AP / "sensitivity_realdata_bdg2" / "tables" / "real_building_shapes_hemisphere_shifted.csv").rename(columns={"nz_month": "month"})
        for lab in bd.building_id.unique():
            rows += run(ni, nat, bd[bd.building_id == lab][["month", "is_weekend", "hour", "norm_weight"]], ["month", "is_weekend", "hour"], "norm_weight", "bdg2", lab)
D = pd.DataFrame(rows); D.to_csv(OUT / "six_order_sensitivity.csv", index=False)

r1 = lambda x: round(float(x), 1); r2 = lambda x: round(float(x), 2)
o = {}
for tag, d in D.groupby("set"):
    ratio = d.spatial.abs() / d.temporal.abs().replace(0, np.nan)
    o[tag] = {"n": len(d), "spatial_gt_temporal_mean": int((ratio > 1).sum()), "spatial_gt_temporal_all_six_orders": int((d.orders_spatial_gt_temporal == 6).sum()),
              "ratio_min": r2(ratio.min()), "ratio_min_any_order": r2(d.ratio_min_over_orders.min())}
    h = d[(d.scenario == "Reference") & (d.start_year == 2027) & (d.period == 25)]
    o[tag]["headline_total_pct_by_shape"] = {r.load_shape: r1(r.total_pct) for r in h.itertuples()}
    k = d[(d.scenario == "Reference") & (d.start_year == 2027) & (d.period == 10)]
    o[tag]["case_2027_10_total_pct_by_shape"] = {r.load_shape: r1(r.total_pct) for r in k.itertuples()}
p = OUT / "numbers_for_text.json"; N = json.load(open(p, encoding="utf-8")); N["six_order_sensitivity"] = o
json.dump(N, open(p, "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps(o, indent=1))
