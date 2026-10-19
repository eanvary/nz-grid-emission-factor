"""
Flag 3b -- cross-check the 22-reference list in MANUSCRIPT_INTEGRATION_REPORT.md
(section 4, "References to add to the manuscript") against the actual
figures/*_PROVENANCE.md files that cite each source, and write
analysis/REFERENCE_COMPLETENESS_STATUS.csv (ref_key, status, missing_fields).

This is a human checklist, not a fabrication pass: every "missing_fields"
value below is either (a) the same gap the manuscript integration report
itself already flagged with an inline **[INCOMPLETE — VERIFY]** or
**[VERIFY ...]** tag, or (b) a genuine mismatch found by reading the
corresponding *_PROVENANCE.md file next to the reference-list entry. No
missing DOI, author, or volume number is invented anywhere in this file.

Two issues surfaced ONLY by the provenance cross-check (not already flagged
in the integration report):
  - ref #18 (EPA eGRID2022): LITERATURE_AXIS_REGISTER.csv's egrid_cambium_2025
    row attributes its magnitude to "EPA eGRID / NREL Cambium 2025", but
    FIG8_PROVENANCE.md confirms the actual fetch used ONLY EPA eGRID2022 --
    no NREL Cambium 2025 citation exists anywhere in the reference list or
    provenance docs. The Cambium half of that attribution is uncited.
  - ref #20 (NESO Carbon Intensity API): FIG8_PROVENANCE.md confirms this was
    "fetched live" with no access/query date recorded in either the
    provenance doc or the reference-list entry itself, even though the
    reference list's own text says to "record access date if used in the
    manuscript" -- that instruction was never carried out.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "REFERENCE_COMPLETENESS_STATUS.csv"

# (ref_key, status, missing_fields) -- ref numbers below match
# MANUSCRIPT_INTEGRATION_REPORT.md section 4, in the same order.
ROWS = [
    ("graff_zivin_2014", "complete", ""),  # 1 -- full author list + DOI present
    ("siler_evans_2012", "complete", ""),  # 2
    ("weber_2010", "complete", ""),  # 3
    ("e3s_china_2024", "complete", ""),  # 4 -- Dong, Gu & Zhang 2024, DOI 10.1051/e3sconf/202458002008, found via web search 2026-08-23; publisher page 403'd on direct fetch so primary text itself unread, magnitude_verified stays "no"
    ("zou_2026", "complete", ""),  # 5 -- full author list, volume 412, article 127655, DOI 10.1016/j.apenergy.2026.127655 confirmed by reading the primary PDF directly, 2026-08-23
    ("bontekoe_2024", "complete", ""),  # 6 -- DOI 10.1016/j.enbuild.2024.114499 confirmed via primary-source cross-check (ScienceDirect record), 2026-08-23
    ("schafer_2024", "complete", ""),  # 7
    ("g7_nzeb_2025", "incomplete", "author list; volume; DOI"),  # 8
    ("goldsworthy_aryai_2023", "incomplete", "volume; issue; DOI"),  # 9
    ("ten_questions_2026", "incomplete", "author list; DOI"),  # 10
    ("future_grid_wblca_2024", "incomplete", "author list"),  # 11
    ("ijlca_2022_dynamic_mix", "incomplete", "article title; author list"),  # 12
    ("london_office_2025", "incomplete", "author list"),  # 13
    ("german_prospective_ef_2026", "incomplete", "author list"),  # 14
    ("austrian_prospective_lca_2024", "incomplete", "venue and full citation not captured -- cannot be traced to a specific publication; may need to be dropped"),  # 15
    ("li_2023", "complete", ""),  # 16 -- independently verified against primary text (Table 5/6)
    ("cer_canada", "complete", ""),  # 17
    ("egrid_cambium_2025", "incomplete", "NREL Cambium 2025 citation missing from the reference list -- register attributes the magnitude to both EPA eGRID2022 AND NREL Cambium 2025, but FIG8_PROVENANCE.md confirms only eGRID2022 (ref #18) was actually fetched/cited; the Cambium 2025 half is uncited"),  # 18
    ("dcceew_australia", "complete", ""),  # 19
    ("neso_2025", "incomplete", "access/query date for the live API not recorded, despite the reference list's own instruction to record it"),  # 20
    ("stjacques_canada_ontario", "incomplete", "full citation not captured (author initials, exact year, volume, DOI)"),  # 21
    ("eea_2024_eu27", "complete", ""),  # 22
]

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["ref_key", "status", "missing_fields"])
    w.writerows(ROWS)

n_complete = sum(1 for _, s, _ in ROWS if s == "complete")
n_incomplete = sum(1 for _, s, _ in ROWS if s == "incomplete")
print(f"Wrote {OUT.name}: {len(ROWS)} references, complete={n_complete}, incomplete={n_incomplete}")
print("\nIncomplete references:")
for rk, s, m in ROWS:
    if s == "incomplete":
        print(f"  {rk}: {m}")
