"""
Paper 03, Figure 2 (validation) -- data-driven build from the primary database files.

Every panel and every statistic quoted in the paper's Section 2.4 is computed here, in one
pass, from the database itself (no intermediate figure tables):

  (a) Quarterly national EF, 2015Q1-2026Q1
        this study, full scope   : output/monthly_emission_factor_NI_SI.csv (sum CO2 / sum gen, both islands)
        this study, MBIE scope   : raw EA_EMI_raw/*_Generation_MD.csv plus the flagged fills, cogeneration
                                   removed by EMI's own Tech_Code ("Cogen"), factors from the pipeline's
                                   shared attribution (generation_pipeline/fuel_attribution.py) -- same
                                   logic as validate_ef_database_2015_2025.py D2
        MBIE published           : generation_pipeline/MBIE_Quarterly_Electricity_Emissions_2026Q1.xlsx,
                                   sheet "Electricity EFs", CO2 + 28*CH4 + 265*N2O
  (b) Daily national generation by fuel, this study vs em6, 2026
        this study : generation_by_fuel_daily_2026.csv (built from raw EMI by build_2026_extension_and_em6_crosscheck.py)
        em6        : em6_free_generation_by_fuel_daily.csv (em6 free feed), trading_date shifted +1 day (UTC vs NZT;
                     see fix_em6_dayshift_and_rebuild_crosscheck.py)
  (c) North Island monthly EF, metered vs projected Reference, 2024-2025
        metered   : output/hourly_emission_factor_NI_SI.csv, generation-weighted (sum CO2 / sum gen)
        projected : output/edgs/edgs_hourly_emission_factor.parquet weighted by NI generation from
                    edgs_hourly_generation.parquet -- like-for-like generation weighting on both sides.

Writes paper03_fig2_validation.json (series + statistics) next to this script.
Run with the analysis_paper venv.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "generation_pipeline"))
from fuel_attribution import FuelAttribution, poc_island_map  # noqa: E402

out = {"built": pd.Timestamp.now().isoformat(timespec="seconds"), "stats": {}}
QMAP = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}
MB_LABEL = {1: "Mar", 2: "Jun", 3: "Sep", 4: "Dec"}

# (a) MBIE published
xl = pd.ExcelFile(ROOT / "generation_pipeline" / "MBIE_Quarterly_Electricity_Emissions_2026Q1.xlsx")
dfm = xl.parse("Electricity EFs", header=None)
mb = pd.DataFrame({"mblabel": dfm.iloc[8, 1:].tolist(), "co2": dfm.iloc[10, 1:].tolist(),
                   "ch4": dfm.iloc[11, 1:].tolist(), "n2o": dfm.iloc[12, 1:].tolist()}).dropna(subset=["mblabel"])
mb["mbie"] = mb["co2"] + mb["ch4"] * 28 + mb["n2o"] * 265

# this study, full scope
m = pd.read_csv(ROOT / "output" / "monthly_emission_factor_NI_SI.csv")
nat = m.groupby(["year", "month"]).agg(gen=("total_gen_MWh", "sum"), co2=("total_CO2_kg", "sum")).reset_index()
nat["q"] = pd.to_datetime(nat[["year", "month"]].assign(day=1)).dt.to_period("Q")
qa = nat.groupby("q").agg(gen=("gen", "sum"), co2=("co2", "sum")).reset_index()
qa["full"] = qa.co2 / qa.gen

# this study, MBIE scope (cogeneration removed by Tech_Code), factors from fuel_attribution.py
fa = FuelAttribution()
g = fa.generation(level="month", include_fills=True, exclude_cogen=True)
g = g[g["poc"].map(poc_island_map()).isin(["NI", "SI"])]  # as the pipeline (every POC maps; no rows drop)
g = fa.attribute(g)
g = g.rename(columns={"gen_mwh": "gen", "co2_kg": "co2", "year": "y", "month": "mo"})
g["q"] = pd.to_datetime(g[["y", "mo"]].rename(columns={"y": "year", "mo": "month"}).assign(day=1)).dt.to_period("Q")
qe = g.groupby("q").agg(gen=("gen", "sum"), co2=("co2", "sum")).reset_index()
qe["excl"] = qe.co2 / qe.gen

qq = qa[["q", "full"]].merge(qe[["q", "excl"]], on="q")
qq["mblabel"] = qq.q.apply(lambda p: f"{MB_LABEL[p.quarter]} {str(p.year)[2:]}")
qq = qq.merge(mb[["mblabel", "mbie"]], on="mblabel", how="inner").sort_values("q")
qq["label"] = qq.q.apply(lambda p: f"{p.year} {QMAP[p.quarter]}")
out["panel_a"] = [[l, round(a, 2), round(b, 2), round(c, 2)] for l, a, b, c in zip(qq.label, qq.full, qq.excl, qq.mbie)]
out["stats"]["a"] = {
    "n_quarters": int(len(qq)), "first": qq.label.iloc[0], "last": qq.label.iloc[-1],
    "r_full": round(qq.full.corr(qq.mbie), 4), "r_excl": round(qq.excl.corr(qq.mbie), 4),
    "mad_full_pct": round(((qq.full - qq.mbie).abs() / qq.mbie * 100).mean(), 2),
    "mad_excl_pct": round(((qq.excl - qq.mbie).abs() / qq.mbie * 100).mean(), 2)}

# (b) em6
EM6 = {"GAS": "GAS", "CG": "CLG", "HYD": "HYD", "WIN": "WIN", "SOL": "SOL", "GEO": "GEO"}
ours = pd.read_csv(HERE / "generation_by_fuel_daily_2026.csv", parse_dates=["trading_date"])
em6 = pd.read_csv(HERE / "em6_free_generation_by_fuel_daily.csv", parse_dates=["trading_date"])
em6["fuel_std"] = em6.fuel_em6.map(EM6); em6 = em6.dropna(subset=["fuel_std"])
em6["trading_date"] = em6.trading_date + pd.Timedelta(days=1)
lo, hi = max(ours.trading_date.min(), em6.trading_date.min()), min(ours.trading_date.max(), em6.trading_date.max())
c = ours[(ours.trading_date >= lo) & (ours.trading_date <= hi)].merge(em6[(em6.trading_date >= lo) & (em6.trading_date <= hi)], on=["trading_date", "fuel_std"])
out["panel_b"] = {f: [[round(a / 1000, 3), round(b / 1000, 3)] for a, b in zip(s.gen_mwh, s.gen_mwh_em6)] for f, s in c.groupby("fuel_std")}
out["stats"]["b"] = {"n_days": int(c.trading_date.nunique()), "first": str(lo.date()), "last": str(hi.date()),
                     "by_fuel": {f: {"r": round(s.gen_mwh.corr(s.gen_mwh_em6), 3),
                                     "mean_abs_diff_pct": round(((s.gen_mwh - s.gen_mwh_em6).abs() / s.gen_mwh_em6.replace(0, np.nan) * 100).mean(), 1),
                                     "ratio_em6_over_ours": round((s.gen_mwh_em6 / s.gen_mwh.replace(0, np.nan)).mean(), 2),
                                     "days_em6_zero": int((s.gen_mwh_em6 <= 0).sum())} for f, s in c.groupby("fuel_std")}}

# (c) projection vs metered, NI
h = pd.read_csv(ROOT / "output" / "hourly_emission_factor_NI_SI.csv", parse_dates=["datetime"])
h = h[(h.island == "NI") & (h.datetime.dt.year.isin([2024, 2025]))].dropna(subset=["EF_kg_per_MWh"])
ef_ = pd.read_parquet(ROOT / "output" / "edgs" / "edgs_hourly_emission_factor.parquet")
ef_ = ef_[(ef_.scenario == "Reference") & (ef_.island == "NI") & (ef_.ef_basis == "generation")]
gen = pd.read_parquet(ROOT / "output" / "edgs" / "edgs_hourly_generation.parquet", columns=["datetime_hour", "scenario", "island", "generation_mwh"])
gen = gen[(gen.scenario == "Reference") & (gen.island == "NI")].groupby("datetime_hour").generation_mwh.sum().rename("gen").reset_index()
p = ef_.merge(gen, on="datetime_hour"); p["dt"] = pd.to_datetime(p.datetime_hour)
p = p[p.dt.dt.year.isin([2024, 2025])]
p["kg"] = p.emission_factor_kg_co2e_per_kwh * 1000 * p.gen  # kgCO2e per hour (EF kg/kWh x MWh x 1000)
h["ym"] = h.datetime.dt.to_period("M").astype(str); p["ym"] = p.dt.dt.to_period("M").astype(str)
hm = h.groupby("ym").apply(lambda s: s.total_CO2_kg.sum() / s.total_gen_MWh.sum()).rename("metered")
pm = p.groupby("ym").apply(lambda s: s.kg.sum() / s.gen.sum()).rename("projected")
mm = pd.concat([hm, pm], axis=1).reset_index()
out["panel_c"] = [[a, round(b, 1), round(cc, 1)] for a, b, cc in zip(mm.ym, mm.metered, mm.projected)]
sc = {}
for y in (2024, 2025):
    hy, py = h[h.datetime.dt.year == y], p[p.dt.dt.year == y]
    hw, pw = hy.total_CO2_kg.sum() / hy.total_gen_MWh.sum(), py.kg.sum() / py.gen.sum()
    j = hy.set_index("datetime").EF_kg_per_MWh.to_frame("h").join(py.set_index("dt").emission_factor_kg_co2e_per_kwh.mul(1000).rename("p"), how="inner")
    sc[str(y)] = {"metered_kg_per_mwh": round(hw, 1), "projected_kg_per_mwh": round(pw, 1), "gap_pct": round((pw / hw - 1) * 100, 1), "hourly_r": round(j.h.corr(j.p), 2)}
hw2 = h.total_CO2_kg.sum() / h.total_gen_MWh.sum(); pw2 = p.kg.sum() / p.gen.sum()
sc["pooled_gap_pct"] = round((pw2 / hw2 - 1) * 100, 1)
sc["basis"] = "generation-weighted on both sides (sum CO2 / sum generation)"
out["stats"]["c"] = sc
# scope check: the metered database counts geothermal fugitive CO2; the projection follows MBIE's
# combustion-only scope and counts none. Share taken from hourly_fuel_mix_NI_SI.csv (same raw EMI source).
fm = pd.read_csv(HERE / "hourly_fuel_mix_NI_SI.csv", parse_dates=["date"])
fm = fm[(fm.island == "NI") & (fm.date.dt.year.isin([2024, 2025]))]
for y in (2024, 2025):
    f = fm[fm.date.dt.year == y]
    share = f[f.fuel_std == "GEO"].co2_kg.sum() / f.co2_kg.sum()
    met = sc[str(y)]["metered_kg_per_mwh"]; prj = sc[str(y)]["projected_kg_per_mwh"]
    adj = met * (1 - share)
    sc[str(y)].update({"geothermal_share_of_metered_co2_pct": round(share * 100, 1),
                       "metered_excl_geothermal_kg_per_mwh": round(adj, 1),
                       "gap_excl_geothermal_pct": round((prj / adj - 1) * 100, 1)})
    pg = gen_by_fuel = None
out["stats"]["c"] = sc

json.dump(out, open(HERE / "paper03_fig2_validation.json", "w", encoding="utf-8"), indent=1)
print(json.dumps(out["stats"], indent=1))
