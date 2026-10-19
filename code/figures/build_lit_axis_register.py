"""
Build analysis/LITERATURE_AXIS_REGISTER.csv: the source register for Fig. 1
(evidence map) and Table 1 (magnitude register), for the "Where, when, and
which future" manuscript.

Sources read (not hardcoded numbers below are transcribed verbatim from
these files; source_line records where in the source file each row's claim
comes from):
  - analysis (compass scan): PhD/Papers/01 Review Paper/Refeences/
        compass_artifact_wf-5b35d95c-e67d-5586-b845-ab455e896ab3_text_markdown.md
  - uncertainty-typology paper: PhD/Proposal/meetings/20260519/
        1-s2.0-S0360132323008065-main.md  (Li et al. 2023, Building and Environment)
  - this study: analysis_paper/FINDINGS_REGISTER.md (F1, F10)
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "LITERATURE_AXIS_REGISTER.csv"

COLUMNS = [
    "ref_key", "authors_short", "year", "venue", "doi", "domain", "grid_system",
    "axis_spatial", "axis_temporal", "axis_trajectory", "factor_basis",
    "magnitude_value", "magnitude_axis", "spatial_boundary_used",
    "in_review_corpus", "source_line",
]

COMPASS = "compass_artifact_wf-5b35d95c-e67d-5586-b845-ab455e896ab3_text_markdown.md"
LI2023 = "1-s2.0-S0360132323008065-main.md"
FINDINGS = "FINDINGS_REGISTER.md"

rows = [
# Theme A: spatial resolution studies
dict(ref_key="graff_zivin_2014_spatial", authors_short="Graff Zivin et al.", year=2014,
     venue="Journal of Economic Behavior & Organization 107(A):248-268",
     doi="10.1016/j.jebo.2014.03.010", domain="ev_transport", grid_system="USA (Midwest vs West)",
     axis_spatial="quantified", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="marginal",
     magnitude_value=">3x (marginal emission rates, upper Midwest vs western US)",
     magnitude_axis="spatial", spatial_boundary_used="US regions (Midwest vs West)",
     in_review_corpus="no", source_line=f"{COMPASS} L11, L32"),
dict(ref_key="graff_zivin_2014_temporal", authors_short="Graff Zivin et al.", year=2014,
     venue="Journal of Economic Behavior & Organization 107(A):248-268",
     doi="10.1016/j.jebo.2014.03.010", domain="ev_transport", grid_system="USA (Midwest vs West)",
     axis_spatial="quantified", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="marginal",
     magnitude_value=">2x (marginal rates, some hours of day vs others, within region)",
     magnitude_axis="temporal", spatial_boundary_used="US regions (Midwest vs West)",
     in_review_corpus="no", source_line=f"{COMPASS} L11, L32"),
dict(ref_key="siler_evans_2012", authors_short="Siler-Evans et al.", year=2012,
     venue="Environmental Science & Technology 46(9):4742-4748", doi="10.1021/es300145v",
     domain="power_sector", grid_system="USA (Midwest vs West)",
     axis_spatial="quantified", axis_temporal="absent", axis_trajectory="absent",
     factor_basis="marginal",
     magnitude_value="~70% more avoided CO2/MWh (Midwest vs West, equivalent efficiency measure)",
     magnitude_axis="spatial", spatial_boundary_used="US regions (Midwest vs West, eGRID-based)",
     in_review_corpus="no", source_line=f"{COMPASS} L12, L32"),
dict(ref_key="weber_2010", authors_short="Weber et al.", year=2010,
     venue="Environmental Science & Technology 44(6):1895-1901", doi="10.1021/es9017909",
     domain="power_sector", grid_system="USA eGRID subregions",
     axis_spatial="quantified", axis_temporal="absent", axis_trajectory="absent",
     factor_basis="average",
     magnitude_value="~0.65 kgCO2/kWh (eGRID subregion vs national average difference)",
     magnitude_axis="spatial", spatial_boundary_used="eGRID subregion",
     in_review_corpus="no", source_line=f"{COMPASS} L34, L67"),
dict(ref_key="e3s_china_2024_spatial", authors_short="E3S Web of Conf. (celct2024)", year=2024,
     venue="E3S Web of Conferences, art. 02008", doi="",
     domain="power_sector", grid_system="China",
     axis_spatial="quantified", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="20.59% (spatial resolution, largest of 3 deviation sources)",
     magnitude_axis="spatial", spatial_boundary_used="provincial/regional grid (China)",
     in_review_corpus="no", source_line=f"{COMPASS} L13, L50, L58"),
dict(ref_key="e3s_china_2024_temporal", authors_short="E3S Web of Conf. (celct2024)", year=2024,
     venue="E3S Web of Conferences, art. 02008", doi="",
     domain="power_sector", grid_system="China",
     axis_spatial="quantified", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="5.01% (temporal resolution)",
     magnitude_axis="temporal", spatial_boundary_used="provincial/regional grid (China)",
     in_review_corpus="no", source_line=f"{COMPASS} L13, L50, L58"),
dict(ref_key="neso_2025", authors_short="NESO Carbon Intensity API", year=2025,
     venue="National Energy System Operator (with EDF Europe, Oxford, WWF)", doi="",
     domain="power_sector", grid_system="UK (14 DNO regions)",
     axis_spatial="quantified", axis_temporal="discussed", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="~220 gCO2e/kWh (SW England) vs ~129 (GB avg), 2025",
     magnitude_axis="spatial", spatial_boundary_used="DNO region (UK)",
     in_review_corpus="no", source_line=f"{COMPASS} L38"),
# Theme B: temporal resolution studies
dict(ref_key="zou_2026", authors_short="Zou, Raftery, Roberts et al.", year=2026,
     venue="Applied Energy", doi="",
     domain="building_lca", grid_system="USA (18 grid regions)",
     axis_spatial="absent", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="median errors typically <10% (season-hour/month-hour vs hourly factors)",
     magnitude_axis="temporal", spatial_boundary_used="grid region (18 US ISO/RTO regions)",
     in_review_corpus="no", source_line=f"{COMPASS} L16"),
dict(ref_key="bontekoe_2024", authors_short="Bontekoe et al.", year=2024,
     venue="Energy and Buildings 319:114499", doi="",
     domain="building_lca", grid_system="Netherlands / France / Sweden",
     axis_spatial="absent", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="underestimated 67% (FR), 19% (SE); max EFD 149 kgCO2 (NL)",
     magnitude_axis="temporal", spatial_boundary_used="national average",
     in_review_corpus="no", source_line=f"{COMPASS} L17"),
dict(ref_key="schafer_2024", authors_short="Schäfer, Cerdas & Herrmann", year=2024,
     venue="Energy & Environmental Science 17(8):2776-2786", doi="10.1039/D3EE04394K",
     domain="methodology_review", grid_system="multi-country (65-reference review)",
     axis_spatial="discussed", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="-28% (Spain) to +69% (Switzerland) (hourly vs annual resolution effect)",
     magnitude_axis="temporal", spatial_boundary_used="national average (review scope)",
     in_review_corpus="no",
     source_line=f"{COMPASS} L18, L60, L67 -- explicitly declines to quantify spatial resolution "
                  "'because data on how the spatial resolution influences grid EF is lacking'"),
dict(ref_key="g7_nzeb_2025", authors_short="G7 NZEB dynamic-EF study", year=2025,
     venue="Building and Environment", doi="",
     domain="building_lca", grid_system="France (Paris) / USA (New York)",
     axis_spatial="absent", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="understates 111% (Paris); overstates up to 120% (New York)",
     magnitude_axis="temporal", spatial_boundary_used="national/city average",
     in_review_corpus="no", source_line=f"{COMPASS} L42"),
dict(ref_key="goldsworthy_aryai_2023", authors_short="Goldsworthy & Aryai", year=2023,
     venue="Sustainable Energy Technologies and Assessments", doi="",
     domain="building_lca", grid_system="Australia",
     axis_spatial="absent", axis_temporal="discussed", axis_trajectory="absent",
     factor_basis="both",
     magnitude_value="", magnitude_axis="",
     spatial_boundary_used="national average", in_review_corpus="no",
     source_line=f"{COMPASS} L42 -- time-varying average vs marginal factors discussed, no single "
                 "headline magnitude reported in the scan"),
dict(ref_key="ten_questions_2026", authors_short="\"Ten questions...\" review", year=2026,
     venue="Building and Environment", doi="",
     domain="methodology_review", grid_system="multi-country (review anchor)",
     axis_spatial="discussed", axis_temporal="discussed", axis_trajectory="absent",
     factor_basis="", magnitude_value="", magnitude_axis="",
     spatial_boundary_used="", in_review_corpus="no",
     source_line=f"{COMPASS} L42 -- synthesis/review anchor citing both Siler-Evans (spatial) and "
                 "temporal studies, no own quantified magnitude"),
# Theme C: trajectory / temporal-evolution studies
dict(ref_key="future_grid_wblca_2024", authors_short="\"Future grid mix impacts...\"", year=2024,
     venue="Environmental Research: Infrastructure and Sustainability", doi="10.1088/2634-4505/adc154",
     domain="building_lca", grid_system="USA",
     axis_spatial="absent", axis_temporal="absent", axis_trajectory="discussed",
     factor_basis="average",
     magnitude_value="", magnitude_axis="",
     spatial_boundary_used="national average (annual)", in_review_corpus="no",
     source_line=f"{COMPASS} L21 -- 56 scenarios to 2100, 60-yr US residential WBLCA; identifies "
                 "grid decarbonisation as an emerging topic, no single headline magnitude reported"),
dict(ref_key="ijlca_2022_dynamic_mix", authors_short="Int. J. LCA (2022)", year=2022,
     venue="International Journal of Life Cycle Assessment", doi="10.1007/s11367-022-02043-y",
     domain="building_lca", grid_system="not specified in scan",
     axis_spatial="absent", axis_temporal="absent", axis_trajectory="discussed",
     factor_basis="average",
     magnitude_value="", magnitude_axis="",
     spatial_boundary_used="national average (static, per source quote)", in_review_corpus="no",
     source_line=f"{COMPASS} L22 -- notes 'current approach ... is to apply a static, average "
                 "national electricity mix'; no magnitude reported in the scan"),
dict(ref_key="london_office_2025", authors_short="London office dynamic-LCA study", year=2025,
     venue="International Journal of Life Cycle Assessment", doi="10.1007/s11367-025-02493-0",
     domain="building_lca", grid_system="UK (London)",
     axis_spatial="absent", axis_temporal="absent", axis_trajectory="quantified",
     factor_basis="",
     magnitude_value="~10% reduction in carbon & embodied impacts (evolving vs static mix)",
     magnitude_axis="trajectory", spatial_boundary_used="national average", in_review_corpus="no",
     source_line=f"{COMPASS} L23"),
dict(ref_key="german_prospective_ef_2026", authors_short="German prospective EF dataset", year=2026,
     venue="Energy, Sustainability and Society", doi="10.1186/s13705-026-00562-2",
     domain="methodology_review", grid_system="Germany",
     axis_spatial="absent", axis_temporal="absent", axis_trajectory="discussed",
     factor_basis="both",
     magnitude_value="", magnitude_axis="",
     spatial_boundary_used="national average, dynamic to 2070", in_review_corpus="no",
     source_line=f"{COMPASS} L24 -- prospective dynamic average/marginal EF dataset to 2070; "
                 "operationalises trajectory dimension, no single magnitude reported in the scan"),
dict(ref_key="austrian_prospective_lca_2024", authors_short="Austrian building-stock prospective LCA", year=2024,
     venue="not specified in scan", doi="",
     domain="building_lca", grid_system="Austria",
     axis_spatial="absent", axis_temporal="absent", axis_trajectory="discussed",
     factor_basis="",
     magnitude_value="", magnitude_axis="",
     spatial_boundary_used="national average", in_review_corpus="no",
     source_line=f"{COMPASS} L24 -- named without a magnitude in the scan"),
# Theme E: analogous heterogeneous grids
dict(ref_key="cer_canada", authors_short="Canadian Energy Regulator / provincial data", year=2024,
     venue="Canadian Energy Regulator; BC EEIF methodology", doi="",
     domain="power_sector", grid_system="Canada (BC/Quebec/Manitoba vs Alberta/Saskatchewan)",
     axis_spatial="quantified", axis_temporal="absent", axis_trajectory="absent",
     factor_basis="",
     magnitude_value=">15x (hydro provinces <30 gCO2/kWh vs Alberta/Saskatchewan 400-600 gCO2/kWh)",
     magnitude_axis="spatial", spatial_boundary_used="provincial grid", in_review_corpus="no",
     source_line=f"{COMPASS} L26, L54"),
dict(ref_key="stjacques_canada_ontario", authors_short="St-Jacques et al. / Canadian consumption-based EF study", year=2019,
     venue="Energy and Buildings", doi="",
     domain="building_lca", grid_system="Canada (Ontario)",
     axis_spatial="discussed", axis_temporal="discussed", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="", magnitude_axis="",
     spatial_boundary_used="provincial/consumption-based", in_review_corpus="no",
     source_line=f"{COMPASS} L54 -- notes only ~2% of surveyed studies considered time-varying "
                 "grid intensity; no single spatial/temporal error magnitude reported in the scan"),
dict(ref_key="dcceew_australia", authors_short="DCCEEW NGA state factors", year=2024,
     venue="Australian National Greenhouse Accounts (NGA)", doi="",
     domain="power_sector", grid_system="Australia (Tasmania vs Victoria)",
     axis_spatial="quantified", axis_temporal="absent", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="up to 4x (Tasmania hydro vs Victoria brown coal, NGA)",
     magnitude_axis="spatial", spatial_boundary_used="state grid (NGA factors)", in_review_corpus="no",
     source_line=f"{COMPASS} L26, L54"),
dict(ref_key="egrid_cambium_2025", authors_short="EPA eGRID / NREL Cambium 2025", year=2025,
     venue="EPA eGRID2023; NREL Cambium 2025", doi="",
     domain="power_sector", grid_system="USA eGRID subregions",
     axis_spatial="quantified", axis_temporal="absent", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="~6-11x subregional range (~39 kgCO2eq/MWh Seattle to ~435 Miami)",
     magnitude_axis="spatial", spatial_boundary_used="eGRID/Cambium subregion", in_review_corpus="no",
     source_line=f"{COMPASS} L26, L54"),
dict(ref_key="nordics_nordpool", authors_short="Nordics (Norway vs Nord Pool)", year=2024,
     venue="not specified in scan", doi="",
     domain="power_sector", grid_system="Nordics",
     axis_spatial="discussed", axis_temporal="absent", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="", magnitude_axis="",
     spatial_boundary_used="bidding zone / national", in_review_corpus="no",
     source_line=f"{COMPASS} L6, L54 -- qualitative only (hydro Norway/Sweden vs wider grid), no "
                 "magnitude reported in the scan"),
# Uncertainty-typology paper (Li et al. 2023)
# NB: known pitfall check -- 910% belongs to M7 (method-related, energy-mix
# SCENARIO = trajectory axis, Grade 2), NOT to DA7 (data-related, time
# RESOLUTION of the energy mix = temporal axis, Grade 1). DA7's own maximum
# fluctuation is 150% (Table 6), not 910%. Kept as two separate rows so the
# two magnitudes cannot be silently pooled.
dict(ref_key="li_2023_da7", authors_short="Li et al.", year=2023,
     venue="Building and Environment 244:110779", doi="10.1016/j.buildenv.2023.110779",
     domain="methodology_review", grid_system="multi-country (97-publication SLR)",
     axis_spatial="absent", axis_temporal="quantified", axis_trajectory="absent",
     factor_basis="",
     magnitude_value="max 150%, avg 69% (DA7: time resolution of energy mix)",
     magnitude_axis="temporal", spatial_boundary_used="", in_review_corpus="no",
     source_line=f"{LI2023} L440-442, L486-491 (Table 6)"),
dict(ref_key="li_2023_m7", authors_short="Li et al.", year=2023,
     venue="Building and Environment 244:110779", doi="10.1016/j.buildenv.2023.110779",
     domain="methodology_review", grid_system="multi-country (97-publication SLR)",
     axis_spatial="absent", axis_temporal="absent", axis_trajectory="quantified",
     factor_basis="",
     magnitude_value="3%-910% (M7: energy mix scenario, Grade 2, 55-80% studies most-influential)",
     magnitude_axis="trajectory", spatial_boundary_used="", in_review_corpus="no",
     source_line=f"{LI2023} L34 (abstract), L436, L466-469 (Table 5), L622 (conclusion)"),
# This study
dict(ref_key="this_study", authors_short="This study", year=2026,
     venue="Building and Environment (submitted)", doi="",
     domain="building_lca", grid_system="New Zealand (North/South Island, MBIE EDGS)",
     axis_spatial="quantified", axis_temporal="quantified", axis_trajectory="quantified",
     factor_basis="average",
     magnitude_value="120-352% of total decomposition error (spatial component, F1)",
     magnitude_axis="spatial", spatial_boundary_used="island (NI/SI)", in_review_corpus="yes",
     source_line=f"{FINDINGS} F1 (L17-53), F10 (L221-225)"),
]

for r in rows:
    r["year"] = int(r["year"])

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS)
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f"Wrote {OUT} ({len(rows)} rows)")
for r in rows:
    print(f"  {r['ref_key']:<32} spatial={r['axis_spatial']:<10} temporal={r['axis_temporal']:<10} "
          f"trajectory={r['axis_trajectory']:<10} basis={r['factor_basis']:<8} mag_axis={r['magnitude_axis']}")
