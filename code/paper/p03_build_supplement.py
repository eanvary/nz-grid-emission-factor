# -*- coding: utf-8 -*-
"""Build the supplementary material for the 30 September 2026 revision (python-docx).
Every value comes from Figure/analysis_v1/out (numbers_for_text.json and CSVs), the review coding
file, or text moved out of the 24 September manuscript. Usage: python p03_build_supplement.py <out.docx>"""
import json, sys
from pathlib import Path
import pandas as pd
from docx import Document
from docx.shared import Pt

HERE = Path(__file__).resolve().parent; OUTD = HERE / "out"; FIG = HERE.parent
N = json.load(open(OUTD / "numbers_for_text.json", encoding="utf-8"))
doc = Document(); st = doc.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(11)
M = "−"


def p(t): doc.add_paragraph(t)
def h(t, l=1): doc.add_heading(t, level=l)
def table(cols, rows, caption):
    doc.add_paragraph(caption).runs[0].bold = True
    t = doc.add_table(rows=1, cols=len(cols)); t.style = "Table Grid"
    for i, c in enumerate(cols): t.rows[0].cells[i].text = str(c)
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r): cells[i].text = str(v)
    for row in t.rows:
        for c in row.cells:
            for par in c.paragraphs:
                for run in par.runs: run.font.size = Pt(9)
    doc.add_paragraph("")
def n1(x): return (M + f"{abs(x):.1f}") if x < 0 else f"{x:.1f}"


doc.add_heading("Supplementary material", 0)
p("Where, when, and which future: decomposing grid emission factor error in building life cycle assessment. "
  "Database: New Zealand grid emission factor database, ef-database-v1.0.1; projection on the primary consistent-scope variant.")

h("S1. Scoping review: eligibility, search, and exclusions")
p("Eligibility was framed by population, concept, context, outcome, and study type. The population was existing or retrofitted non-residential "
  "buildings, with NZ office and commercial stock as the primary case. The concept was life cycle or whole-life carbon assessment with a recognised "
  "system boundary. The context was NZ decarbonisation policy and its international comparators. The outcomes were reported carbon values, the grid "
  "factor used, and any stated data gaps. Study types were peer-reviewed articles, theses, and agency or industry reports published in English from "
  "2010 to March 2026.")
p("Scopus and ScienceDirect were the primary databases, searched to March 2026. Google Scholar and the BRANZ Research Portal lack advanced query syntax "
  "and served as secondary sources, with hand searches of three journals. After deduplication, 333 records were screened on title and abstract, then "
  "full text. By stage, 243 records were excluded on title and abstract, 10 reports were not retrieved, and 12 were excluded on full text. Of the 265 exclusions, 74 concerned residential-only populations, 56 new construction without an existing-building assessment, 78 had no "
  "NZ data or context and none of the three Group 2 features below, 45 had no carbon quantification, two were late-stage duplicates, and 10 failed other criteria, leaving 68 included records. "
  "Each excluded record is counted once, under the first of these reasons that applies in the order duplicate, residential only, new construction only, no carbon quantification, no NZ context. "
  "A targeted sweep for NZ context and policy documents contributed seven of the 333 screened records.")
p("Group 2 records qualified through one of three methodological features: a carbon assessment of an existing or retrofitted non-residential building, "
  "a comparison of assessment tools, or a review of assessment method. The review was screened by a single reviewer, and identification-stage counts "
  "were recovered from the screening log.")
p("Coding. The six disclosure attributes were coded from the full text of every record, and a supporting quotation from the record's own assessment, with its "
  "position in the text, was recorded for each positive code. Passages that describe other studies were not counted. EN 15978 or an equivalent standard counts as cited "
  "when the record's assessment follows it; ISO 14040 and ISO 14044 count as equivalent. A source counts as named when the record ties a dataset, agency factor, cited report, or sourced value "
  "to grid electricity. A spatial resolution counts as stated only for a sub-national factor. A temporal resolution counts as stated for an annual or multi-year "
  "average as well as a sub-annual one; no record states a sub-annual one. A trajectory counts as stated when the record's own assessment applies or tests a factor "
  "that changes over the assessment period. A platform is recorded when the record's assessment is run in it; a tool used only for energy simulation, as a data source, "
  "or for validation is not counted.")
import csv as _csv
_ag = list(_csv.DictReader(open(FIG / "analysis" / "fulltext_coding_20261013" / "agreement.csv", encoding="utf-8")))
_lab = {"operational_carbon_quantified": "Operational carbon quantified", "en15978_cited": "EN 15978 or equivalent cited", "source_named": "Grid factor source named",
        "spatial_stated": "Spatial resolution stated", "temporal_stated": "Temporal resolution stated", "trajectory_stated": "Trajectory stated"}
_rows = []
for k, v in _lab.items():
    a = [x for x in _ag if x["attribute"] == k]
    _rows.append([v, sum(x["first_pass"] == "True" for x in a), sum(x["full_text"] == "True" for x in a), f"{sum(x['first_pass'] == x['full_text'] for x in a)} of {len(a)}"])
_S1B = _rows
cod = pd.read_csv(FIG / "analysis" / "FIG3_DISCLOSURE_CODING_20261013_labelled.csv")
yn = lambda v: "yes" if str(v).strip().lower() in ("1", "true", "yes", "y") else "no"
table(["Record", "Group", "Platform", "Operational carbon", "EN 15978", "Factor source", "Sub-national factor", "Averaging period", "Trajectory"],
      [[r.label, r.Segmentation_Group, r.platform, yn(r.col1_opcarbon), yn(r.col2_en15978), yn(r.col3_gridef), yn(r.col4_spatial), yn(r.col5_temporal), yn(r.col6_trajectory)]
       for r in cod.itertuples()],
      "Table S1. The 68 reviewed records: evidence group, calculation platform, and disclosure coding (records are listed by citation; full references at the end of this file).")

h("S2. Scope of the historical database and the projection")
p("Both series count combustion carbon dioxide at the Ministry for the Environment 2025 gross factors (natural gas 54.06, coal 91.99, and diesel 69.20 t CO2/TJ) "
  "applied to plant heat rates, and geothermal fugitive emissions by station. The NZ Steel Glenbrook plant burns off-gas from coal-based ironmaking, and "
  "the national inventory reports those emissions under industrial processes, so the plant carries zero in the electricity factor. In the projection, "
  "7.63 PJ a year of Glenbrook-class coal carries zero. Geothermal intensities follow station-level values reported by the operators and the NZ "
  "Geothermal Association, with a documented proxy order where a station has no value.")
p("The denominator is grid-injected generation. In the projection, grid generation equals MBIE's electricity emissions divided by MBIE's grid emission "
  "factor, scaled by k = 0.9741, the 2015 to 2023 mean ratio of metered generation to that implied value, with the same share on each island. This "
  "share is an estimate. MBIE's published emissions are reproduced by a combustion-only variant to 5.9%; the consistent-scope projection differs by "
  f"{N['check2_primary']['emissions_weighted_abs_dev_pct']}% by design.")

h("S3. Validation details")
p("Internal checks. The historical database passes 38 of 44 automated checks and fails none; the other six are explained warnings or information-only "
  "checks. Generation and emission totals reconcile exactly across hourly, daily, monthly, and annual levels, and no hour carries a negative value.")
p("MBIE quarterly factor. Removing cogeneration from the metered record widens the mean difference from 9.8% to 13.1%, because MBIE's totals include "
  "cogeneration fuel that the metered record sees only as exports to the grid.")
p("Projection against MBIE. The projection matches MBIE's generation by trajectory, year, and fuel in all 1,350 combinations and its peak in all 135 "
  "trajectory-years, both exact by construction. The largest emissions difference is in 2050 under Environmental (21.6% low).")
p("em6 cross-check. Solar agrees in shape with this database (r = 0.97), but em6 reports 1.66 times the volume throughout; the cause of this steady offset "
  "is not yet resolved. Coal is excluded because the free feed reports no coal on 48 of the 169 days. The hourly emission-factor comparison over 2015 to "
  "2025 requires the paid historical feed and remains open.")
p("Uncertainty band. Each hourly value carries a band computed by Approach 2 of the IPCC (2019) guidance. In 50,000 Monte Carlo trials each fuel's factor "
  "took one lognormal multiplier drawn from its published range, held across the record. The mean 95% band on NI hours, 2015 to 2025, is 12.5% of the "
  "point value, and no hour has a negative lower bound.")
p("Benchmarks. Schäfer et al. (2024) recreated the official German factors for 2020 within 1.2% of the International Energy Agency figure, 4.5% of the "
  "European Environment Agency figure, and 11.8% to 20.8% of the German Environment Agency figures. G. J. Miller et al. (2023) built an hourly, plant-level "
  "dataset for the United States and validated it on 2021 annual totals against earlier datasets. The quarterly comparison here covers 45 quarters, adds "
  "a second measured source at daily resolution and an uncertainty band on every hourly value, and checks the projection against the metered record.")
ov = N["overlap_chain"]
p(f"Overlap. The median absolute hourly deviation between projected and metered NI factors is {ov['2024']['median_abs_dev_pct']:.0f}% in 2024 and "
  f"{ov['2025']['median_abs_dev_pct']:.0f}% in 2025.")

DBV = Path("C:/Users/ehsan/OneDrive - AUT University/PhD/Database/Grid Emission Factor")
d3 = pd.read_csv(DBV / "output" / "D3_fuel_level_validation.csv"); d3 = d3[d3.resolution == "annual"]
lab = {"CLG": "Coal emissions (kt CO2e)", "GAS-PJ": "Gas used for generation (PJ)", "GAS-emissions": "Gas emissions (kt CO2e)", "GEO": "Geothermal emissions (kt CO2e)"}
note = {"CLG": "same plant", "GAS-PJ": "same plant", "GAS-emissions": "MBIE includes most cogeneration gas", "GEO": "no scope-matched target (information only)"}
table(["Quantity", "Years", "Mean |difference| (%)", "Range (%)", "Scope"],
      [[lab[c], "2015 to 2025", f"{x.gap_pct.abs().mean():.1f}", f"{n1(x.gap_pct.min())} to {n1(x.gap_pct.max())}", note[c]] for c, x in d3.groupby("check", sort=False)],
      "Table S2a. Fuel-level comparison of the metered record with MBIE's energy statistics (MBIE, 2026a, 2026b).")
tn = pd.read_csv(DBV / "reference_data" / "times_nz_3" / "derived" / "times_nz3_vs_edgs_vs_metered.csv")
an = pd.read_csv(DBV / "output" / "annual_emission_factor_NI_SI.csv").groupby("year")[["total_CO2_kg", "total_gen_MWh"]].sum()
rows = []
for y in (2023, 2024, 2025):
    t = tn[(tn.Scenario == "Steady") & (tn.Period == y)].iloc[0]
    rows.append([y, f"{t.EF_reported:.1f}", f"{an.loc[y].total_CO2_kg / an.loc[y].total_gen_MWh:.1f}"])
table(["Year", "TIMES-NZ 3.0.8, Steady, national (gCO2e/kWh)", "This study, metered national (gCO2e/kWh)"], rows,
      "Table S2b. Independent model comparison (EECA & BusinessNZ Energy Council, 2026). The TIMES-NZ factor is electricity-sector emissions as reported over total generation, including rooftop and embedded plant; its geothermal emissions are held at 692 kt a year in 2024 to 2026.")
from docx.shared import Cm
doc.add_picture(str(FIG / "Figure S1 - Validation against fuel statistics and TIMES-NZ.png"), width=Cm(16))
doc.add_paragraph("Figure S1. Independent checks of the emission factor database: (a) coal emissions and (b) gas used for generation, metered record "
  "against MBIE's energy statistics, 2015 to 2025; (c) national emission factor, metered record, this study's projection (consistent scope, "
  "grid-injection basis), and TIMES-NZ 3.0.8 (reported scope, total generation), 2015 to 2050.").runs[0].bold = True
p("Figure S1 (a) and (b) show the like-for-like fuel quantities of Table S2a year by year: the metered record follows MBIE's coal emissions and "
  "gas use within 6% in every year. Gas emissions are not plotted, because MBIE's total includes cogeneration gas that the metered record excludes.")
p("Figure S1 (c) extends the TIMES-NZ comparison beyond 2025. The two sets of pathways are paired by storyline: TIMES-NZ Steady with MBIE's "
  "Reference, and TIMES-NZ Shift with MBIE's Innovation. TIMES-NZ agrees with the metered record in 2023 (72 against 68 gCO2e/kWh) but sits "
  "below it in 2024 and 2025, which it models rather than calibrates to outturn. From 2025 to 2031 TIMES-NZ is 8 to 22 gCO2e/kWh below this study's "
  "projection, because its least-cost dispatch runs less thermal plant; part of the gap is scope, since TIMES-NZ divides by total generation, "
  "including rooftop and embedded plant. The Shift and Innovation pathways converge from 2032, within 8 gCO2e/kWh. After 2035 TIMES-NZ Steady "
  "rises to 59 gCO2e/kWh by 2050, driven by diesel peaking plant, while the Reference pathway stays near 35. The independent model therefore "
  "supports the direction of the projection to the mid-2030s, at a lower level. Beyond that the two models disagree, which is itself a trajectory "
  "uncertainty of the kind the decomposition isolates.")
p("Overlap volumes. In 2024 the projection's Reference trajectory ran 1.1 TWh of coal generation against 1.7 TWh metered; in 2025 it ran 3.1 TWh of gas against 3.8 TWh metered, and in both years 10.4 TWh of geothermal against 8.4 and 9.2 TWh metered. The remaining overlap gap is therefore a scenario difference, not a scope difference.")

h("S4. Template selection")
table(["Year", "Hydro rank (1 = driest)", "Hour-of-day r", "Day-of-week r", "Month-of-year r"],
      [[r["year"], r["hydro_rank_driest_first"], f"{r['corr_hour_of_day']:.3f}", f"{r['corr_day_of_week']:.3f}", f"{r['corr_month_of_year']:.3f}"] for r in N["template_selection"]],
      "Table S3a. Correlation of each metered year's profile with the 2024 to 2025 metered shape.")
SO = N["six_order_sensitivity"]
table(["Template", "Cases with spatial > temporal in all six orders", "Minimum ratio, six-order mean", "Minimum ratio, any order", "Headline total error (%)"],
      [[k.replace("template_", ""), f"{v['spatial_gt_temporal_all_six_orders']} of {v['n']}", f"{v['ratio_min']:.2f}", f"{v['ratio_min_any_order']:.2f}",
        n1(v["headline_total_pct_by_shape"]["daytime_office"])] for k, v in SO.items() if k.startswith("template_")],
      f"Table S3b. Ranking by shape template (headline case 2027 to 2050, daytime office). January 2030 NI hourly factor across templates: {N['jan2030_span_all_templates'][0]:.0f} to {N['jan2030_span_all_templates'][1]:.0f} gCO2e/kWh.")

h("S5. Cases with suppressed component shares")
D = pd.read_csv(OUTD / "decomposition_by_island_basis.csv")
g = D[(D.island == "NI") & (D.basis == "generation")]
sm = g[g.total_pct_of_resolved.abs() < 5]
table(["Profile", "Trajectory", "Start", "Period", "Total (kgCO2e/m²)", "Total (%)", "Temporal", "Spatial", "Trajectory"],
      [[r.load_shape, r.scenario, r.start_year, r.period, n1(r.total_kgm2), n1(r.total_pct_of_resolved), n1(r.temporal_kgm2), n1(r.spatial_kgm2), n1(r.trajectory_kgm2)] for r in sm.itertuples()],
      "Table S4. Generation-basis cases with a total error within 5% of the resolved value (absolute terms; components are six-order means).")

h("S6. Accounting basis, building island, and practice factor")
rows = []
for isl in ("NI", "SI"):
    for b in ("generation", "consumption"):
        x = D[(D.island == isl) & (D.basis == b)]
        rt = (x.spatial.abs() / x.temporal.abs().replace(0, float("nan")))
        rows.append([isl, b, int((x.spatial.abs() > x.temporal.abs()).sum()), f"{rt.min():.2f}" if rt.notna().any() else "–",
                     int((x.total < 0).sum()), int((x.total > 0).sum())])
table(["Building island", "Basis", "Spatial > temporal (of 105)", "Minimum ratio", "Cases understated", "Cases overstated"], rows,
      "Table S5. Summary of the 105-case decomposition by building island and accounting basis (six-order means).")
T4 = N["NI_generation"]["table4"]
rng = lambda o, f: f"{n1(o[f])} ({n1(o[f + '_min'])} to {n1(o[f + '_max'])})"
table(["Profile and trajectory", "Temporal", "Spatial", "Trajectory"], [[k.replace("|", ", ").replace("_", " "), rng(o, "temporal"), rng(o, "spatial"), rng(o, "trajectory")] for k, o in T4.items()],
      "Table S5b. Components of the headline case (2027 to 2050, NI, generation basis): mean over the six orders of the three steps, with the range across orders in brackets (kgCO2e/m²).")
pc = N["NI_generation"]["practice_c_by_trajectory"]
table(["Trajectory", "Cases", "Cases understated", "Error range (% of resolved value)"], [[k, v["n"], v["understates"], f"{n1(v['pct_min'])} to {n1(v['pct_max'])}"] for k, v in pc.items()],
      "Table S5c. National annual factor that follows the trajectory (treatment c) against the resolved value, NI, generation basis. The case has the structure of the LCAQuick default since version 3.3, computed on this study's series and not with the tool's own factor.")
bd = SO["bdg2"]
p(f"Metered office shapes. With the six metered offices and their mean, the spatial component exceeds the temporal component in {bd['spatial_gt_temporal_all_six_orders']} of {bd['n']} cases in all six orders. "
  f"The minimum ratio is {bd['ratio_min']:.2f} for the six-order mean and {bd['ratio_min_any_order']:.2f} in any single order.")
pa = pd.read_csv(OUTD / "practice_anchor.csv")
table(["Start year", "Period", "Resolved", "Static, projected", "Static, MfE 2025", "Total with MfE factor", "Total (%)"],
      [[r.start_year, r.period, r.resolved_kgm2, r.static_projected_kgm2, r.static_mfe_kgm2, n1(r.total_mfe_kgm2), n1(r.total_mfe_pct)] for r in pa.itertuples()],
      "Table S6. Practice factor: MfE annual grid-average factor for 2025, 0.0786625 kgCO2e/kWh (MfE, 2026a, Table 5.2), NI daytime office, Reference.")

h("S7. Screening bound for other grids")
table(["Grid system", "Understatement in the highest-intensity sub-region (%)", "National average / lowest sub-region"],
      [[r["system"], r["understatement_highest_subregion_pct"], "–" if r["national_over_lowest"] is None else r["national_over_lowest"]] for r in N["screening_bound"]],
      "Table S7. Static spatial error bound, (maximum − national) / maximum, from the values behind Figure 8.")

h("S8. Temporal error by year")
te = pd.read_csv(OUTD / "temporal_error_by_year.csv")
pv = te[te.year.isin([2025, 2030, 2040, 2050])].pivot_table(index=["load_shape", "year"], columns="scenario", values="temporal_pct").round(1)
table(["Profile", "Year"] + list(pv.columns), [[a, b] + [n1(v) for v in r] for (a, b), r in pv.iterrows()],
      "Table S8. Annual temporal error of the NI factor by year (%, positive = the annual mean overstates that year's carbon).")

h("S9. Reproducibility")
p("Scripts in Figure/analysis_v1: p03_build_primary_inputs.py (projection inputs on the primary variant), p03_run_chain.py (analysis steps, run one at a time), "
  "p03_new_analyses.py (the 105-case decomposition over six orders and every quoted number, numbers_for_text.json), p03_six_order_sensitivity.py, p03_temporal_by_year.py, and this file. The working copy is a "
  "git archive of ef-database-v1.0.1. The database and the scripts are in the public repository named in the data availability statement.")

# ---- references cited in this supplement (Table S1 records and the sources in S1 to S9)
sys.path.insert(0, str(HERE))
from p03_supp_refs import add_refs
print("supplement references:", add_refs(doc, FIG / "excel" / "_build_scripts" / "references_20261012.txt", h))
doc.save(sys.argv[1]); print("saved", sys.argv[1])
