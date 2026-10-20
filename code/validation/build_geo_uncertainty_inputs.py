"""
Geothermal inputs for the uncertainty propagation: uncertainty by proxy-rule step
(RULE_GEO_PROXY_ORDER) rather than one between-station sigma for the whole fleet.

Geothermal CO2 is split into independent pseudo-fuels:
  GEO             step 1 (source-specific intensity for that station and year).
                  rel_sigma = sqrt(AD^2 + EF^2) from NIR 2026 Vol 1, section 3.2.3, Table 3.2.3
                  "Uncertainty for New Zealand's energy sector emission estimates for 2024" (printed
                  pp72-73): "Fugitive - Other forms of energy production (geothermal)", activity data
                  +/-5.0%, emission factor +/-5.0% (CO2; the CH4 row gives the same), so 7.07%.
  GEO_S2_<station> step 2 (the same station's nearest published year, including 2025 values held
                  from 2024 and every 2026 month). rel_sigma = sqrt(7.07%^2 + s_station^2), where
                  s_station is the station's own year-to-year relative variation in the NZGA series:
                  RMS of year-on-year relative changes, 2015-2024, published values only, pairs with a
                  zero previous value skipped. A station with fewer than 3 published years takes the
                  pooled value (RMS over all stations' year-on-year changes). One term per station, so
                  station errors are independent.
  GEO_PROXY       steps 3 and 4 (same-field or composite proxy; NZGA fleet average). rel_sigma = the
                  MW-weighted between-station spread of McLean and Richardson (2019), 93.97%
                  (geothermal_mclean_richardson_stations.csv).
Step classification is per generator-month, from the attribution rule and the basis recorded in
generation_pipeline/geothermal_intensity_nzga.csv. The hourly file splits each hour's GEO row by that
month's shares of geothermal generation and CO2 by term (an approximation: geothermal output is close
to flat within a month).
Outputs (this folder): geo_uncertainty_sigma.csv (one row per term, with s_station),
geo_step2_station_variation.csv, monthly_fuel_mix_uncertainty.csv, hourly_fuel_mix_uncertainty.csv.
"""
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import FuelAttribution, poc_island_map  # noqa: E402

NIR_AD, NIR_EF = 5.0, 5.0
SIG_MEASURED = math.sqrt(NIR_AD ** 2 + NIR_EF ** 2) / 100.0
g = pd.read_csv(HERE / "geothermal_mclean_richardson_stations.csv")
mu = (g.mw * g.ef_gco2_kwh).sum() / g.mw.sum()
SIG_PROXY = math.sqrt((g.mw * (g.ef_gco2_kwh - mu) ** 2).sum() / g.mw.sum()) / mu

# Each station's own year-to-year variation in the NZGA series, 2015-2024
basis = pd.read_csv(ROOT / "generation_pipeline" / "geothermal_intensity_nzga.csv")
pub = basis[(basis.basis == "published") & basis.year.between(2015, 2024) & (basis.station != "NZGA MW-weighted average")]
var_rows, pooled = [], []
for st, d in pub.groupby("station"):
    d = d.sort_values("year").set_index("year").g_co2e_per_kwh
    rel = [(d[y] - d[y - 1]) / d[y - 1] for y in d.index if y - 1 in d.index and d[y - 1] > 0]
    var_rows.append({"station": st, "n_published_years": len(d), "n_changes": len(rel),
                     "s_station_own": float(np.sqrt(np.mean(np.square(rel)))) if rel else np.nan})
    if len(d) >= 3:
        pooled += rel
S_POOLED = float(np.sqrt(np.mean(np.square(pooled))))
var = pd.DataFrame(var_rows)
var["s_station_used"] = np.where(var.n_published_years >= 3, var.s_station_own, S_POOLED)
var["basis"] = np.where(var.n_published_years >= 3, "own series", "pooled (fewer than 3 published years)")
var["rel_sigma_step2"] = np.sqrt(SIG_MEASURED ** 2 + var.s_station_used ** 2)
var.to_csv(HERE / "geo_step2_station_variation.csv", index=False, float_format="%.4f")
print(f"GEO step 1 rel_sigma = {SIG_MEASURED:.4f}; steps 3-4 rel_sigma = {SIG_PROXY:.4f}; pooled s_station = {S_POOLED:.4f}")
print(var.round(4).to_string(index=False))
S2 = var.set_index("station")


def term(st):
    return "GEO_S2_" + re.sub(r"[^A-Za-z0-9]+", "_", st).strip("_")


sig_rows = [{"fuel_std": "GEO", "rel_sigma": SIG_MEASURED, "step": "1", "station": "", "s_station": np.nan,
             "source": "NIR 2026 Vol 1 s3.2.3 Table 3.2.3 (printed pp72-73): geothermal AD +/-5.0%, EF +/-5.0%; sqrt(5^2+5^2)"},
            {"fuel_std": "GEO_PROXY", "rel_sigma": SIG_PROXY, "step": "3-4", "station": "", "s_station": np.nan,
             "source": "McLean and Richardson (2019) 12-station MW-weighted spread (geothermal_mclean_richardson_stations.csv)"}]

# Step classification per generator-month
held = {(r.station, int(r.year)) for r in basis.itertuples() if "held" in str(r.basis).lower()}
proxy34 = {(r.station, int(r.year)) for r in basis.itertuples()
           if any(k in str(r.basis).lower() for k in ("proxy", "composite"))}
fa = FuelAttribution()
isl = poc_island_map()
gen = fa.generation("month")
gen = gen[gen.fuel_std == "GEO"].copy()
gen["island"] = gen.poc.map(isl)
gen = gen[gen.island.isin(["NI", "SI"])]
a = fa.attribute(gen.groupby(["poc", "gen_code", "fuel_std", "year", "month", "island"], as_index=False).gen_mwh.sum())


def classify(r):
    rule = r.rule
    if "FALLBACK" in rule or "+" in rule:
        return "GEO_PROXY"                                  # step 4, or a blend with a step-3 proxy
    st = rule.replace("GEO_NZGA_", "").replace("_NEARESTYEAR", "")
    if st.startswith("Onepu") or (r.gen_code == "kawerau_(topp2)" and st == "TOPP1") or (st, int(r.year)) in proxy34:
        return "GEO_PROXY"                                  # step 3 (same-field or composite proxy)
    if "_NEARESTYEAR" in rule or (st, int(r.year)) in held:
        return term(st)                                     # step 2 (the station's nearest published year)
    return "GEO"                                            # step 1


a["group"] = [classify(r) for r in a.itertuples()]
for st in sorted({r.rule.replace("GEO_NZGA_", "").replace("_NEARESTYEAR", "") for r in a.itertuples() if r.group.startswith("GEO_S2_")}):
    if st not in S2.index:  # no NZGA series (e.g. Te Huka 3, operator figure only): fewer than 3 years, so pooled
        S2.loc[st] = {"n_published_years": 0, "n_changes": 0, "s_station_own": np.nan, "s_station_used": S_POOLED,
                      "basis": "pooled (no NZGA series)", "rel_sigma_step2": math.sqrt(SIG_MEASURED ** 2 + S_POOLED ** 2)}
        print(f"  {st}: no NZGA series, pooled s_station {S_POOLED:.4f}")
    sig_rows.append({"fuel_std": term(st), "rel_sigma": float(S2.loc[st, "rel_sigma_step2"]), "step": "2", "station": st,
                     "s_station": float(S2.loc[st, "s_station_used"]),
                     "source": f"sqrt(7.07%^2 + s_station^2), s_station {S2.loc[st, 'basis']} (NZGA series 2015-2024, geothermal_intensity_nzga.csv)"})
pd.DataFrame(sig_rows).to_csv(HERE / "geo_uncertainty_sigma.csv", index=False)
m = a.groupby(["island", "year", "month", "group"], as_index=False)[["gen_mwh", "co2_kg"]].sum()
tot = m.groupby(["island", "year", "month"])[["gen_mwh", "co2_kg"]].transform("sum")
m["sg"] = m.gen_mwh / tot.gen_mwh
m["sc"] = (m.co2_kg / tot.co2_kg.where(tot.co2_kg > 0, np.nan)).fillna(0.0)
ni = m[m.island == "NI"].assign(step=lambda x: np.where(x.group == "GEO", "1", np.where(x.group == "GEO_PROXY", "3-4", "2")))
print("NI geothermal CO2 share by step and year:")
print((ni.groupby(["year", "step"]).co2_kg.sum() / ni.groupby("year").co2_kg.sum()).unstack().round(3).to_string())
shares = m[["island", "year", "month", "group", "sg", "sc"]]

# Monthly fuel mix with GEO split
mm = pd.read_csv(ROOT / "output" / "monthly_fuel_mix_NI_SI.csv")
geo = mm[mm.fuel_code == "GEO"].merge(shares, on=["island", "year", "month"], how="left")
geo["group"] = geo.group.fillna("GEO"); geo["sg"] = geo.sg.fillna(1.0); geo["sc"] = geo.sc.fillna(1.0)
x = geo.copy()
x["fuel_code"] = x.group
x["gen_mwh"] = geo.gen_mwh * geo.sg
x["co2_kg"] = geo.co2_kg * geo.sc
x["share_pct"] = geo.share_pct * geo.sg
x["weighted_ef_kg_per_MWh"] = np.where(x.gen_mwh > 0, x.co2_kg / x.gen_mwh.where(x.gen_mwh > 0, 1.0), 0.0)
if "filled_gen_mwh" in x:
    x["filled_gen_mwh"] = geo.filled_gen_mwh * geo.sg
if "co2_kg_estimated" in x:
    x["co2_kg_estimated"] = geo.co2_kg_estimated * geo.sc
out_m = pd.concat([mm[mm.fuel_code != "GEO"], x.drop(columns=["group", "sg", "sc"])], ignore_index=True)
out_m = out_m.sort_values(["island", "year", "month", "fuel_code"])
out_m.to_csv(HERE / "monthly_fuel_mix_uncertainty.csv", index=False)
assert abs(out_m.co2_kg.sum() - mm.co2_kg.sum()) < 1e-6 * max(1.0, mm.co2_kg.sum())

# Hourly fuel mix with GEO split (monthly shares)
hm = pd.read_csv(HERE / "hourly_fuel_mix_NI_SI.csv")
hm["year"] = hm["date"].str[:4].astype(int)
hm["month"] = hm["date"].str[5:7].astype(int)
hg = hm[hm.fuel_std == "GEO"].merge(shares, on=["island", "year", "month"], how="left")
hg["group"] = hg.group.fillna("GEO"); hg["sg"] = hg.sg.fillna(1.0); hg["sc"] = hg.sc.fillna(1.0)
y = hg.copy()
y["fuel_std"] = y.group
y["gen_mwh"] = hg.gen_mwh * hg.sg
y["co2_kg"] = hg.co2_kg * hg.sc
y["ef_kg_per_mwh"] = np.where(y.gen_mwh > 0, y.co2_kg / y.gen_mwh.where(y.gen_mwh > 0, 1.0), 0.0)
out_h = pd.concat([hm[hm.fuel_std != "GEO"], y.drop(columns=["group", "sg", "sc"])], ignore_index=True).drop(columns=["year", "month"])
out_h.to_csv(HERE / "hourly_fuel_mix_uncertainty.csv", index=False)
print(f"Wrote monthly_fuel_mix_uncertainty.csv ({len(out_m)} rows), hourly_fuel_mix_uncertainty.csv ({len(out_h):,} rows); "
      f"hourly CO2 check {out_h.co2_kg.sum() / 1e9:.4f} vs {hm.co2_kg.sum() / 1e9:.4f} Mt; terms: {len(sig_rows)}")
