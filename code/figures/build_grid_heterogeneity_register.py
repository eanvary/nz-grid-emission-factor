"""
Build analysis/GRID_HETEROGENEITY_REGISTER.csv -- the source register for
Fig. 8 (the paper's transferability argument).

Literature rows (Canada, USA, Australia, UK, Nordic) were checked against
primary sources at build time via WebFetch/WebSearch, not taken from the
international-scan document (analysis/.../compass_artifact_...md), which is
treated only as a lead list per the brief. The verification trail for each
row -- URL fetched, what was found, what failed -- is recorded in the `note`
column here and in figures/FIG8_PROVENANCE.md.

The New Zealand row is computed from this study's own tables at run time,
not typed.
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"
OUT = ROOT / "analysis" / "GRID_HETEROGENEITY_REGISTER.csv"

COLUMNS = ["system", "sub_region_unit", "n_sub_regions", "min_intensity", "max_intensity",
           "unit", "national_average", "ratio_max_min", "reference_year", "primary_source",
           "source_type", "verified", "source_url_or_doi", "note"]

# =============================================================================
# New Zealand -- computed from this study's own tables, headline reference
# year (2027, Reference scenario, generation-basis), matching the headline
# case used throughout the rest of this figure set.
# =============================================================================
REF_SCENARIO, REF_YEAR = "Reference", 2027
isl = pd.read_csv(TABLES / "phase3_annual_island_ef.csv")
nat = pd.read_csv(TABLES / "phase3_annual_national_ef.csv")
isl_sub = isl[(isl["scenario"] == REF_SCENARIO) & (isl["year"] == REF_YEAR)]
ni_val = isl_sub[isl_sub["island"] == "NI"]["annual_island_ef"].iloc[0]
si_val = isl_sub[isl_sub["island"] == "SI"]["annual_island_ef"].iloc[0]
nat_val = nat[(nat["scenario"] == REF_SCENARIO) & (nat["year"] == REF_YEAR)]["annual_national_ef"].iloc[0]

nz_min_kg, nz_max_kg = min(ni_val, si_val), max(ni_val, si_val)
nz_min_g, nz_max_g, nz_nat_g = nz_min_kg * 1000, nz_max_kg * 1000, nat_val * 1000
nz_ratio = (nz_max_g / nz_min_g) if nz_min_g > 0 else float("nan")

print(f"NZ (computed): NI={ni_val:.6f} kgCO2e/kWh ({ni_val*1000:.2f} g/kWh), "
      f"SI={si_val:.6f} kgCO2e/kWh ({si_val*1000:.2f} g/kWh), "
      f"national={nat_val:.6f} kgCO2e/kWh ({nat_val*1000:.2f} g/kWh), "
      f"ratio={'undefined (min=0)' if pd.isna(nz_ratio) else f'{nz_ratio:.1f}'}")

rows = [
# --- Canada: CER Provincial and Territorial Energy Profiles, 2022 data,
# fetched directly (5 of 13 provinces/territories checked: the ones named
# in the international scan) ---
dict(system="Canada", sub_region_unit="province", n_sub_regions=5,
     min_intensity=1.2, max_intensity=660, unit="gCO2e/kWh", national_average=100,
     ratio_max_min=round(660 / 1.2, 1), reference_year=2022,
     primary_source="Canada Energy Regulator, Provincial and Territorial Energy Profiles "
                     "(Quebec min; Nova Scotia max; Alberta, Saskatchewan, Manitoba also checked)",
     source_type="primary_agency", verified="yes",
     source_url_or_doi="https://www.cer-rec.gc.ca/en/data-analysis/energy-markets/"
                        "provincial-territorial-energy-profiles/",
     note="Fetched directly per-province (Alberta 470, Saskatchewan 630, Nova Scotia 660, "
          "Manitoba 1.3, Quebec 1.2 gCO2e/kWh, all 2022). Only 5 of 13 provinces/territories "
          "checked (those named in the scan) -- not an exhaustive 13-jurisdiction scan; BC, "
          "Newfoundland, PEI, New Brunswick and the 3 territories not checked, true national "
          "min/max could differ."),
# --- USA: EPA eGRID2022 Summary Tables, Table 1, fetched directly ---
dict(system="USA", sub_region_unit="eGRID subregion", n_sub_regions=22,
     min_intensity=274.6, max_intensity=1479.6, unit="lb/MWh", national_average=823.1,
     ratio_max_min=round(1479.6 / 274.6, 2), reference_year=2022,
     primary_source="US EPA eGRID2022 Summary Tables (Table 1, Subregion Output Emission "
                     "Rates), created 2024-01-30",
     source_type="primary_agency", verified="yes",
     source_url_or_doi="https://www.epa.gov/system/files/documents/2024-01/"
                        "egrid2022_summary_tables.pdf",
     note="CO2 (not CO2e) total output emission rate, contiguous US only -- AK/HI/PR "
          "subregions excluded for a like-for-like continental comparison (min=NYUP, "
          "max=MROE). This ratio (~5.4x) is smaller than the scan's cited '~6-11x "
          "Cambium 2025' figure -- Cambium is a different, forward-looking NREL dataset, "
          "not eGRID2022 historical output rates; the scan's number does not reproduce "
          "against this primary source and is not used."),
# --- Australia: DCCEEW NGA Factors 2025, Table 1 -- confirmed directly.
# Automated fetching from this session was blocked on every route tried
# (WebFetch to the PDF/XLSX, in-app Browser); the user downloaded the PDF
# themselves and it was converted locally with pdf_to_md.py, which recovered
# Table 1 verbatim, in full agreement with the blog-compiled values used in
# the first draft of this register. ---
dict(system="Australia", sub_region_unit="state/regional grid", n_sub_regions=8,
     min_intensity=0.20, max_intensity=0.78, unit="kgCO2-e/kWh", national_average=0.62,
     ratio_max_min=round(0.78 / 0.20, 2), reference_year="FY2025-26 (financial year ending June)",
     primary_source="DCCEEW National Greenhouse Accounts Factors 2025, Table 1 "
                     "(Indirect location-based scope 2 emission factors for electricity, "
                     "p.8) -- confirmed verbatim against the primary PDF",
     source_type="primary_agency", verified="yes",
     source_url_or_doi="https://www.dcceew.gov.au/sites/default/files/documents/"
                        "national-greenhouse-account-factors-2025.pdf",
     note="Automated fetching was blocked on every route tried this session (WebFetch to "
          "4 PDF years and the XLSX -- ECONNRESET every time; in-app Browser direct nav "
          "and click-through -- denied/silent download; Claude-in-Chrome not connected). "
          "The user downloaded the PDF directly and it was converted locally with "
          "pdf_to_md.py (PyMuPDF/pymupdf4llm); Table 1 recovered cleanly and matches the "
          "blog-compiled values used in the first draft exactly, including the national "
          "average (0.62) and the NT/DKIS and WA-SWIS/NWIS split rows. Data year is a "
          "financial year (ending June), not a calendar year, per the table's own notes."),
# --- UK: NESO Carbon Intensity API, regional endpoint, fetched live ---
dict(system="UK", sub_region_unit="DNO region", n_sub_regions=14,
     min_intensity=0, max_intensity=376, unit="gCO2/kWh", national_average=235,
     ratio_max_min=float("nan"), reference_year="2026-08-16 (instantaneous, not annual -- see note)",
     primary_source="National Energy System Operator (NESO), Carbon Intensity API, "
                     "regional endpoint (live query)",
     source_type="operator_data", verified="yes",
     source_url_or_doi="https://api.carbonintensity.org.uk/regional",
     note="This is a live INSTANTANEOUS forecast snapshot (single timestamp), not an "
          "annual mean like every other row in this register -- not strictly comparable "
          "on a like-for-like temporal basis. Minimum of 0 gCO2/kWh (North Scotland) "
          "reflects a high-wind instant, not a true annual floor; ratio_max_min is "
          "undefined (min=0) and reported as such rather than computed. 14 genuine DNO "
          "regions used; the API's 3 country-level aggregate rows (England/Scotland/"
          "Wales) excluded."),
# --- Europe (EU27, country-level): replaces the earlier "Nordic/European
# bidding zones" row. Per-bidding-zone (NO1-NO5/SE1-SE4) intensity is not
# officially published at that granularity by any single primary agency
# found (it would have to be computed from ENTSO-E per-zone generation-mix
# data, which is raw generation data, not a published emission-factor
# table) -- but a second search round found the EEA's own country-level EU27
# indicator, fetched and independently re-verified twice against the raw
# CSV (see FIG8_PROVENANCE.md). This is now europe-country-level, fully
# primary-agency-verified, not a bidding-zone comparison -- a genuine
# substitution, not a stand-in for the missing row.
dict(system="Europe (EU27, country-level)", sub_region_unit="country", n_sub_regions=27,
     min_intensity=8, max_intensity=693, unit="gCO2e/kWh", national_average=258,
     ratio_max_min=round(693 / 8, 1), reference_year=2022,
     primary_source="European Environment Agency (EEA), 'Greenhouse gas emission "
                     "intensity of electricity generation', country-level indicator "
                     "(source data: national emissions reported to UNFCCC/EU Governance "
                     "Regulation; Eurostat complete energy balances nrg_bal_c)",
     source_type="primary_agency", verified="yes",
     source_url_or_doi="https://www.eea.europa.eu/en/analysis/maps-and-charts/"
                        "co2-emission-intensity-15/@@download/file",
     note="Min = Sweden (8 gCO2e/kWh, 2022); max = Estonia (693, oil shale). Nordic EU "
          "members for reference: Finland 62, Denmark 117 (Sweden is the minimum). "
          "national_average = 258, the EU-27 aggregate row itself ('2022,EU-27,258,,'), "
          "read directly from the same primary CSV, not a self-computed country mean. "
          "Norway is NOT in this table (EEA/EU27 scope excludes non-EU Norway) -- "
          "Norwegian sources (NVE/SSB) were checked but did not yield a citable 2022 "
          "figure within the time available, so Norway is omitted rather than "
          "estimated. Raw CSV independently re-fetched three times (all-countries pull, "
          "a full Sweden/Finland/Denmark row dump, and the EU-27 aggregate row alone) "
          "and all three agree exactly."),
# --- New Zealand: this study's own tables ---
dict(system="New Zealand", sub_region_unit="island", n_sub_regions=2,
     min_intensity=round(nz_min_g, 2), max_intensity=round(nz_max_g, 2), unit="gCO2e/kWh",
     national_average=round(nz_nat_g, 2), ratio_max_min=nz_ratio,
     reference_year=REF_YEAR,
     primary_source=f"This study: MBIE EDGS-derived generation-basis annual island EF "
                     f"({REF_SCENARIO} scenario), phase3_annual_island_ef.csv / "
                     f"phase3_annual_national_ef.csv",
     source_type="primary_agency", verified="yes", source_url_or_doi="",
     note=f"NI={ni_val*1000:.1f} g/kWh (max), SI={si_val*1000:.1f} g/kWh (min, exactly "
          f"zero under generation-basis modelling for every scenario/year in this table -- "
          f"checked, not a rounding artefact). ratio_max_min undefined (min=0), reported "
          f"as such. {REF_SCENARIO} scenario, {REF_YEAR} (this paper's headline start year)."),
]

df = pd.DataFrame(rows)[COLUMNS]
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False)

n_verified = int((df["verified"] == "yes").sum())
n_total = len(df)
print(f"\nWrote {OUT} ({n_total} rows)")
print(f"Verified: {n_verified} / {n_total}  ({100*n_verified/n_total:.1f}%)")
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 250)
print(df[["system", "verified", "source_type", "min_intensity", "max_intensity",
          "unit", "ratio_max_min"]].to_string(index=False))
