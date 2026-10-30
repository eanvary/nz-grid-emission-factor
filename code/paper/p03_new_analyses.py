"""
Paper 03, database v1.0.1 (primary projection): the added analyses and every number the
text cites, in one traceable pass. Reads the working copy after p03_build_primary_inputs.py and
p03_run_chain.py. Usage: python p03_new_analyses.py <copy_root> <out_dir>

Writes to <out_dir>:
  decomposition_by_island_basis.csv   105-case decomposition, six orders of the three steps, for (NI, SI) x (generation, consumption)
  practice_anchor.csv                 static treatment with MfE's published national factor
  screening_bound.csv                 static spatial error bound for other grids (Figure 7 register)
  numbers_for_text.json               every number quoted in the manuscript, with its source

Added analyses (A2 to A6):
  A2 South Island building: same demand profiles and trajectories, building island SI.
  A3 Consumption basis: hourly island factor from p03_build_primary_inputs.py (emissions follow
     the exporting island); annual island mean weighted by island load; national as generation.
  A4 Practice anchor: treatment (d) with MfE's annual grid-average factor for purchased
     electricity, 2025 (0.0786625 kg CO2e/kWh; MfE, Measuring Emissions Catalogue 2026, v2026.2,
     Table 5.2; file emission_factors_2026_v2_wide.csv), the latest annual value published.
  A6 Screening bound: for a building in a grid's highest-intensity sub-region, the share by which
     a national average understates its factor, (max - national) / max.
"""
import json, sys
from itertools import permutations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
EDGS = ROOT / "output" / "edgs"; T = ROOT / "analysis_paper" / "tables"
REPO = Path(__file__).resolve().parents[2]
SCEN = ["Reference", "Growth", "Constraint", "Innovation", "Environmental"]
MFE_2025 = 0.0786625
N = {}

eui = pd.read_csv(T / "phase3_eui_derived_v2.csv")
EUI = float(eui[eui.cohort == "pre-2004, Whole Building, NI, electricity-dominant"].iloc[0].eui_median)
shapes = pd.read_csv(T / "phase3_load_shapes_stylised.csv")

ef = pd.read_parquet(EDGS / "edgs_hourly_emission_factor.parquet")
ef["year"] = ef.datetime_hour.dt.year; ef["dow"] = ef.datetime_hour.dt.dayofweek; ef["hour"] = ef.datetime_hour.dt.hour
gen = pd.read_parquet(EDGS / "edgs_hourly_generation.parquet", columns=["scenario", "island", "datetime_hour", "generation_mwh"])
gen = gen.groupby(["scenario", "island", "datetime_hour"], observed=True).generation_mwh.sum().reset_index()
load = pd.read_parquet(EDGS / "edgs_hourly_island_load_primary.parquet")

g = ef[ef.ef_basis == "generation"].merge(gen, on=["scenario", "island", "datetime_hour"], how="left")
g["co2"] = g.emission_factor_kg_co2e_per_kwh * g.generation_mwh.fillna(0)
nat_h = g.groupby(["scenario", "datetime_hour"]).agg(co2=("co2", "sum"), gen=("generation_mwh", "sum")).reset_index()
nat_h["ef"] = nat_h.co2 / nat_h.gen; nat_h["year"] = nat_h.datetime_hour.dt.year
nat_h["dow"] = nat_h.datetime_hour.dt.dayofweek; nat_h["hour"] = nat_h.datetime_hour.dt.hour
nat_y = nat_h.groupby(["scenario", "year"]).apply(lambda x: np.average(x.ef, weights=x.gen), include_groups=False)

FEAS = {}
for sy in (2025, 2027, 2030):
    for L in (10, 25, 30, 60):
        n = min(sy + L - 1, 2050) - sy + 1
        FEAS[(sy, L)] = (n, "out_of_scope" if L == 60 or (L - n) / L > 0.2 else ("full" if n == L else f"truncated_{n}yrs"))
# the 25- and 30-year periods from 2027 both end in 2050 (24 years): keep one
FEAS[(2027, 30)] = (24, "duplicate_window")
HEAD = (2027, 25)   # headline case: 2027 to 2050
FACTORS = ("temporal", "spatial", "trajectory")


def six_orders(V):
    """V[(t, s, j)]: cumulative factor sum with each step applied (1) or not (0). Returns, per
    component, its value in each of the six orders of the three steps."""
    out = {f: [] for f in FACTORS}
    for perm in permutations(range(3)):
        state = [0, 0, 0]; prev = V[(0, 0, 0)]
        for f in perm:
            state[f] = 1; cur = V[tuple(state)]; out[FACTORS[f]].append(cur - prev); prev = cur
    return out


def decompose(island, basis):
    e = ef[(ef.ef_basis == basis) & (ef.island == island)]
    w = (gen.rename(columns={"generation_mwh": "w"}) if basis == "generation" else load.rename(columns={"load_mwh": "w"}))
    e = e.merge(w, on=["scenario", "island", "datetime_hour"], how="left")
    isl_y = e.groupby(["scenario", "year"]).apply(
        lambda x: np.average(x.emission_factor_kg_co2e_per_kwh, weights=x.w.fillna(0)) if x.w.fillna(0).sum() > 0 else 0.0, include_groups=False)
    rows = []
    for shp in shapes.label.unique():
        s = shapes[shapes.label == shp][["dow", "hour", "raw_intensity"]]
        a_y = e.merge(s, on=["dow", "hour"]).groupby(["scenario", "year"]).apply(
            lambda x: np.average(x.emission_factor_kg_co2e_per_kwh, weights=x.raw_intensity), include_groups=False)
        ap_y = nat_h.merge(s, on=["dow", "hour"]).groupby(["scenario", "year"]).apply(
            lambda x: np.average(x.ef, weights=x.raw_intensity), include_groups=False)
        for sc in SCEN:
            for (sy, L), (n, fit) in FEAS.items():
                if fit in ("out_of_scope", "duplicate_window"):
                    continue
                yrs = range(sy, sy + n)
                Ea = sum(a_y[(sc, y)] for y in yrs); Eb = sum(isl_y[(sc, y)] for y in yrs)
                Ec = sum(nat_y[(sc, y)] for y in yrs); Ed = nat_y[(sc, sy)] * n; Eap = sum(ap_y[(sc, y)] for y in yrs)
                # eight treatments: (temporal step, spatial step, trajectory step); static = start-year value held
                V = {(0, 0, 0): Ea, (1, 0, 0): Eb, (0, 1, 0): Eap, (1, 1, 0): Ec,
                     (0, 0, 1): a_y[(sc, sy)] * n, (1, 0, 1): isl_y[(sc, sy)] * n, (0, 1, 1): ap_y[(sc, sy)] * n, (1, 1, 1): Ed}
                so = six_orders(V)
                r = dict(island=island, basis=basis, load_shape=shp, scenario=sc, start_year=sy, period=L, fit_status=fit, n_years=n,
                         E_a=Ea, E_b=Eb, E_c=Ec, E_d=Ed, total=Ed - Ea, temporal_o1=Eb - Ea, spatial_o1=Ec - Eb, trajectory_o1=Ed - Ec,
                         practice_c_minus_a=Ec - Ea,
                         total_pct_of_resolved=100 * (Ed - Ea) / Ea if Ea > 1e-12 else np.nan,
                         practice_c_pct_of_resolved=100 * (Ec - Ea) / Ea if Ea > 1e-12 else np.nan)
                for f in FACTORS:
                    r[f] = float(np.mean(so[f])); r[f + "_min"] = min(so[f]); r[f + "_max"] = max(so[f])
                st = [abs(x) / abs(t) if abs(t) > 1e-15 else np.inf for x, t in zip(so["spatial"], so["temporal"])]
                r["orders_spatial_gt_temporal"] = int(sum(x > 1 for x in st)); r["ratio_min_over_orders"] = min(st)
                r["orders_temporal_negative"] = int(sum(t < 0 for t in so["temporal"]))
                rows.append(r)
    return pd.DataFrame(rows)


D = pd.concat([decompose(i, b) for i in ("NI", "SI") for b in ("generation", "consumption")], ignore_index=True)
KG = ["E_a", "E_c", "E_d", "total", "practice_c_minus_a"] + [f + s for f in FACTORS for s in ("", "_min", "_max", "_o1")]
for c in KG:
    D[c + "_kgm2"] = D[c] * EUI
D.to_csv(OUT / "decomposition_by_island_basis.csv", index=False)

# consistency: NI generation equals the chain's own decomposition table
chain = pd.read_csv(T / "phase3_decomposition_full.csv")
m = D[(D.island == "NI") & (D.basis == "generation")].merge(
    chain, left_on=["load_shape", "scenario", "start_year", "period"], right_on=["load_shape", "scenario", "start_year", "study_period_yrs_requested"])
N["check_NI_generation_vs_chain_max_abs_diff"] = float((m.total - m.total_error_d_minus_a).abs().max())
assert N["check_NI_generation_vs_chain_max_abs_diff"] < 1e-9 and len(m) == 105


def r1(x): return round(float(x), 1)
def r2(x): return round(float(x), 2)


def summary(d, tag):
    o = {}
    ratio = d.spatial.abs() / d.temporal.abs().replace(0, np.nan)
    o["n_rows"] = len(d); o["fit_counts"] = d.fit_status.value_counts().to_dict()
    o["spatial_gt_temporal_mean"] = int((ratio > 1).sum()); o["spatial_gt_temporal_all_six_orders"] = int((d.orders_spatial_gt_temporal == 6).sum())
    o["ratio_min"], o["ratio_median"], o["ratio_max"] = r2(ratio.min()), r2(ratio.median()), r1(ratio.max())
    o["ratio_min_any_order"] = r2(d.ratio_min_over_orders.min())
    o["ratio_min_by_profile"] = {k: r2((x.spatial.abs() / x.temporal.abs()).min()) for k, x in d.groupby("load_shape")}
    o["temporal_sign_differs_across_orders"] = int(((d.orders_temporal_negative > 0) & (d.orders_temporal_negative < 6)).sum())
    o["trajectory_gt_spatial"] = {"n": int((d.trajectory.abs() > d.spatial.abs()).sum()),
                                  "by_scenario": d[d.trajectory.abs() > d.spatial.abs()].scenario.value_counts().to_dict()}
    rel = lambda f: ((d[f + "_max"] - d[f + "_min"]).abs() / d[f].abs().replace(0, np.nan))
    o["order_range_over_mean_pct_max"] = {f: r1(100 * rel(f).max()) for f in FACTORS}
    def row(sh, sc, sy, L):
        x = d[(d.load_shape == sh) & (d.scenario == sc) & (d.start_year == sy) & (d.period == L)].iloc[0]
        return {k: r1(x[k + "_kgm2"]) for k in KG} | {
            "n_years": int(x.n_years), "total_pct": r1(x.total_pct_of_resolved), "practice_c_pct": r1(x.practice_c_pct_of_resolved),
            "spatial_pct_of_resolved": r1(100 * abs(x.spatial) / x.E_a) if x.E_a > 0 else None,
            "spatial_o1_pct_of_resolved": r1(100 * abs(x.spatial_o1) / x.E_a) if x.E_a > 0 else None}
    o["headline"] = row("daytime_office", "Reference", *HEAD)
    o["case_2027_10"] = row("daytime_office", "Reference", 2027, 10)
    o["case_2025_25"] = row("daytime_office", "Reference", 2025, 25)
    o["table4"] = {f"{sh}|{sc}": row(sh, sc, *HEAD) for sh, sc in
                   [("daytime_office", "Reference"), ("continuous_24_7", "Reference"), ("evening_weighted", "Reference"),
                    ("daytime_office", "Growth"), ("daytime_office", "Constraint"), ("daytime_office", "Innovation"), ("daytime_office", "Environmental")]}
    o["by_trajectory"] = {sc: {"n": len(x), "understates": int((x.total < 0).sum()), "overstates": int((x.total > 0).sum()),
                               "pct_min": r1(x.total_pct_of_resolved.min()), "pct_max": r1(x.total_pct_of_resolved.max())} for sc, x in d.groupby("scenario")}
    o["practice_c_by_trajectory"] = {sc: {"n": len(x), "understates": int((x.practice_c_minus_a < 0).sum()),
                                          "pct_min": r1(x.practice_c_pct_of_resolved.min()), "pct_max": r1(x.practice_c_pct_of_resolved.max())} for sc, x in d.groupby("scenario")}
    hd = d[(d.load_shape == "daytime_office") & (d.start_year == HEAD[0]) & (d.period == HEAD[1])]
    o["practice_c_headline_by_trajectory_pct"] = {r.scenario: r1(r.practice_c_pct_of_resolved) for r in hd.itertuples()}
    small = d[d.total_pct_of_resolved.abs() < 5]
    o["within_5pct"] = {"n": len(small), "by_scenario": small.scenario.value_counts().to_dict()}
    o["fig6_daytime_25yr_total_pct"] = d[(d.load_shape == "daytime_office") & (d.period == 25)].pivot(
        index="scenario", columns="start_year", values="total_pct_of_resolved").round(1).to_dict(orient="index")
    N[tag] = o


summary(D[(D.island == "NI") & (D.basis == "generation")], "NI_generation")
summary(D[(D.island == "NI") & (D.basis == "consumption")], "NI_consumption")
si = D[(D.island == "SI")]
N["SI_building"] = {}
for b, x0 in si.groupby("basis"):
    h = x0[(x0.load_shape == "daytime_office") & (x0.scenario == "Reference") & (x0.start_year == HEAD[0]) & (x0.period == HEAD[1])].iloc[0]
    k27 = x0[(x0.load_shape == "daytime_office") & (x0.scenario == "Reference") & (x0.start_year == 2027) & (x0.period == 10)].iloc[0]
    N["SI_building"][b] = {"headline": {k: r1(h[k + "_kgm2"]) for k in ("E_a", "E_d", "total", "spatial", "temporal", "trajectory")}
                           | {"total_pct": r1(h.total_pct_of_resolved) if h.E_a > 0 else None},
                           "case_2027_10": {k: r1(k27[k + "_kgm2"]) for k in ("E_a", "E_d", "total", "spatial")},
                           "overstates_in": int((x0.total > 0).sum()), "n": len(x0), "spatial_positive_in": int((x0.spatial > 0).sum()),
                           "spatial_gt_temporal": int((x0.spatial.abs() > x0.temporal.abs()).sum()),
                           "total_pct_range": [r1(x0.total_pct_of_resolved.min()), r1(x0.total_pct_of_resolved.max())]}

# A4 practice anchor
pa = []
for sy, L in (HEAD, (2027, 10), (2025, 25)):
    x = D[(D.island == "NI") & (D.basis == "generation") & (D.load_shape == "daytime_office") & (D.scenario == "Reference") & (D.start_year == sy) & (D.period == L)].iloc[0]
    Ed_p = MFE_2025 * x.n_years
    pa.append(dict(start_year=sy, period=L, resolved_kgm2=r1(x.E_a * EUI), static_projected_kgm2=r1(x.E_d * EUI), static_mfe_kgm2=r1(Ed_p * EUI),
                   total_mfe_kgm2=r1((Ed_p - x.E_a) * EUI), total_mfe_pct=r1(100 * (Ed_p - x.E_a) / x.E_a),
                   projected_national_start_year_g_per_kwh=r1(1000 * nat_y[("Reference", sy)])))
pd.DataFrame(pa).to_csv(OUT / "practice_anchor.csv", index=False)
N["practice_anchor"] = pa; N["mfe_2025_g_per_kwh"] = r1(1000 * MFE_2025)

# spatial ratio NI/national, annual, Reference
isl = pd.read_csv(T / "phase3_annual_island_ef.csv"); nat = pd.read_csv(T / "phase3_annual_national_ef.csv")
ni = isl[(isl.island == "NI") & (isl.scenario == "Reference")].set_index("year").annual_island_ef
na = nat[nat.scenario == "Reference"].set_index("year").annual_national_ef
N["reference_annual_g_per_kwh"] = {y: {"NI": r1(1000 * ni[y]), "national": r1(1000 * na[y]), "NI_over_national": r2(ni[y] / na[y])} for y in (2024, 2025, 2027, 2030, 2035, 2049, 2050)}

# A6 screening bound
reg = pd.read_csv(REPO / "data" / "literature_review" / "GRID_HETEROGENEITY_REGISTER.csv")
reg.loc[reg.system == "New Zealand", ["max_intensity", "national_average", "reference_year"]] = [r2(1000 * ni[2027]), r2(1000 * na[2027]), "2027"]
reg.to_csv(OUT / "GRID_HETEROGENEITY_REGISTER_v1.csv", index=False)
sb = []
for _, r in reg.iterrows():
    if "instantaneous" in str(r.reference_year) or pd.isna(r.national_average):
        continue
    mx, nv, mn = float(r.max_intensity), float(r.national_average), float(r.min_intensity)
    sb.append(dict(system=r.system, understatement_highest_subregion_pct=r1(100 * (mx - nv) / mx),
                   national_over_lowest=(r1(nv / mn) if mn > 0 else None)))
pd.DataFrame(sb).to_csv(OUT / "screening_bound.csv", index=False); N["screening_bound"] = sb

# temporal structure (Figure 5)
v = pd.read_csv(T / "phase1_variance_decomp_by_island.csv"); v = v[v.island == "NI"]
vr = v[v.scenario == "Reference"].set_index("year")
N["eta2"] = {"season_2024": r1(100 * vr.eta2_season[2024]), "season_2050": r1(100 * vr.eta2_season[2050]),
             "hour_2024": r1(100 * vr.eta2_hour[2024]), "hour_2050": r1(100 * vr.eta2_hour[2050]),
             "hour_2050_by_scenario": {s: r1(100 * x.set_index("year").eta2_hour[2050]) for s, x in v.groupby("scenario")},
             "season_r": {s: [r2(stats.pearsonr(x.year, x.eta2_season)[0]), float(f"{stats.pearsonr(x.year, x.eta2_season)[1]:.1e}")] for s, x in v.groupby("scenario")},
             "hour_r": {s: [r2(stats.pearsonr(x.year, x.eta2_hour)[0]), float(f"{stats.pearsonr(x.year, x.eta2_hour)[1]:.1e}")] for s, x in v.groupby("scenario")}}
ds = pd.read_csv(T / "phase1_distributional_stats.csv")
a, b = ds[ds.year == 2024], ds[ds.year == 2050]
N["distribution"] = {"cv_2024": [r2(a.cv.min()), r2(a.cv.max())], "cv_2050": [r2(b.cv.min()), r2(b.cv.max())],
                     "mean_minus_median_2024": [r1(a.mean_minus_median_pct.min()), r1(a.mean_minus_median_pct.max())],
                     "mean_minus_median_2050": [r1(b.mean_minus_median_pct.min()), r1(b.mean_minus_median_pct.max())],
                     "zero_hours_pct_2024_max": r2(100 * a.frac_hours_zero.max()), "zero_hours_pct_2050": [r2(100 * b.frac_hours_zero.min()), r2(100 * b.frac_hours_zero.max())]}
p = pd.read_csv(T / "phase1_diurnal_shape_persistence.csv"); p = p[(p.island == "NI") & (p.year == 2050)].set_index("scenario").corr_vs_2024
N["diurnal_corr_2050"] = {k: r2(x) for k, x in p.items()}
dp = pd.read_csv(T / "phase1_diurnal_profiles.csv"); dp = dp[dp.island == "NI"]
pk = dp.loc[dp.groupby(["scenario", "year"]).emission_factor_kg_co2e_per_kwh.idxmax()]
N["peak_hour_counts"] = {int(k): int(x) for k, x in pk.hour.value_counts().items()}
cg = pd.read_csv(T / "phase1_cagr_by_scenario_island.csv")
N["cagr_NI_pct_per_yr"] = {r.scenario: r2(r.cagr_pct_per_yr) for r in cg.itertuples() if r.island == "NI"}

# templates
tr = pd.read_csv(T / "phase3_template_ranking_check.csv")
N["templates"] = tr.round(3).to_dict(orient="records")
jan = []
for suf in ("", "_tmpl2017", "_tmpl2023", "_tmpl2024"):
    e = pd.read_parquet(EDGS / f"edgs_hourly_emission_factor{suf}.parquet", filters=[("scenario", "==", "Reference"), ("island", "==", "NI"), ("ef_basis", "==", "generation")])
    e = e[(e.datetime_hour.dt.year == 2030) & (e.datetime_hour.dt.month == 1)]
    jan.append((suf or "central", r1(1000 * e.emission_factor_kg_co2e_per_kwh.min()), r1(1000 * e.emission_factor_kg_co2e_per_kwh.max())))
N["jan2030_NI_hourly_range_by_template"] = jan
N["jan2030_span_all_templates"] = [min(x[1] for x in jan), max(x[2] for x in jan)]

# template selection (metered record; not projection-dependent)
ts = pd.read_csv(T / "phase2_template_shape_selection.csv")
N["template_selection"] = ts[["year", "hydro_rank_driest_first", "corr_hour_of_day", "corr_day_of_week", "corr_month_of_year"]].round(3).to_dict(orient="records")

# BDG2 real offices
bd = pd.read_csv(ROOT / "analysis_paper" / "sensitivity_realdata_bdg2" / "tables" / "real_shape_decomposition_full.csv")
rb = bd.spatial_component.abs() / bd.temporal_component.abs()
mean6 = bd[(bd.load_shape == "SAMPLE_AVERAGE_6_BUILDINGS") & (bd.scenario == "Reference") & (bd.start_year == 2027) & (bd.study_period_yrs_requested == 10)]
N["bdg2"] = {"n": len(bd), "spatial_gt_temporal": int((rb > 1).sum()), "ratio_min": r2(rb.min()), "mean6_2027_10_total_pct": r1(mean6.total_error_pct_of_Ea.iloc[0])}

# overlap (chain table; the Figure 2 script gives the quoted values)
ov = pd.read_csv(T / "phase0_hist_vs_proj_overlap.csv"); ov = ov[ov.island == "NI"].copy(); ov["y"] = pd.to_datetime(ov.datetime_hour).dt.year
N["overlap_chain"] = {int(y): {"hourly_r": r2(x.hist_ef.corr(x.proj_ef)), "median_abs_dev_pct": r1(x.abs_pct_diff.median())} for y, x in ov.groupby("y")}

# projection check against MBIE (database file)
c2 = pd.read_csv(EDGS / "consistent_scope" / "check2_by_variant.csv").set_index("variant")
av = pd.read_csv(EDGS / "consistent_scope" / "annual_ef_by_variant.csv"); av = av[av.variant == "consistent_scope"].copy()
av["gap"] = 100 * (av.NI_kt / av.MBIE_kt - 1); w = av.loc[av.gap.abs().idxmax()]
N["check2_primary"] = {"emissions_weighted_abs_dev_pct": r1(c2.loc["consistent_scope", "check2_emissions_weighted_abs_dev_pct"]),
                       "combustion_only_pct": r1(c2.loc["combustion_only", "check2_emissions_weighted_abs_dev_pct"]),
                       "worst": {"scenario": w.scenario, "year": int(w.year), "gap_pct": r1(w.gap)}}

json.dump(N, open(OUT / "numbers_for_text.json", "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps({k: N[k] for k in ("NI_generation", "NI_consumption", "SI_building", "practice_anchor", "screening_bound")}, indent=1, default=str)[:9000])
