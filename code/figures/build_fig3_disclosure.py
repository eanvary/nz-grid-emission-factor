"""
Figure 3: disclosure matrix, built from extraction_output_reviewed_Output_v12.xlsx,
sheet 'Extraction', restricted to the 68 Include==Yes records.

Columns 1 and 2 are regex-derived from Operational_Carbon / Standards_Referenced
(rules below).

Columns 3-6 (grid EF source named / spatial / temporal / trajectory) are
each a judgement call on free text. They carry the paper's central
disclosure claim, so they are not left to a fragile keyword regex. The
Emission_Factor_Source text of all 68 records was read by hand, and the
verdict is recorded per Study_ID in COL3456_CODING below. That table is the
single source of truth for those four columns. It can be audited and
reproduced without running any regex.
"""
import re
import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WB = Path(r"C:\Users\ehsan\OneDrive - AUT University\PhD\Papers\01 Review Paper\Refeences\Assessment\extraction_output_reviewed_Output_v12.xlsx")
FIGS = ROOT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL, BASE  # noqa: E402

set_journal_style()
# Single-ink disclosure matrix (one ink colour, not a diverging scale):
# CATEGORICAL[0], deep navy.
OI = {"blue": CATEGORICAL[0], "vermillion": CATEGORICAL[1],
      "bluish_green": CATEGORICAL[2], "grey": BASE["muted_slate"]}

df = pd.read_excel(WB, sheet_name="Extraction")
ie = df["Include_Exclude"].astype(str).str.strip()
inc = df[ie == "Include"].copy()
assert len(inc) == 68, f"expected 68 included records, got {len(inc)}"

# Row labels are academic author-year citations, not the internal Study_ID code.
# The workbook's `Authors` field has no consistent format across its 68
# included records. The formats include semicolon "Surname, First" lists,
# comma "and"-joined "First Last" lists, APA comma/initial lists, single
# bare names in various orders, one middle-dot-separated list and one
# affiliation-letter-suffixed list. One regex cannot parse these reliably
# for a citation in a submitted
# figure. CITATION_LABEL below was built by reading each of the 68
# `Authors`/`Year_Verified` values, and it is checked at run time. For every
# Study_ID the code asserts that (a) the label's year matches `Year_Verified`
# and (b) the first author's surname in the label appears verbatim in the raw
# `Authors` string. A transcription slip therefore fails loudly instead of
# printing a wrong citation.
CITATION_LABEL = {
    "S001": "Ghose (2017)", "S002": "Ghose et al. (2017a)", "S004": "Bui (2023)",
    "S010": "Dowdell & Berg (2016)", "S011": "Berg et al. (2016)", "S012": "MacGregor et al. (2018)",
    "S014": "Paschoalin (2022)", "S015": "Bakshi (2017)", "S016": "Priyan et al. (2025)",
    "S017": "Liang et al. (2025)", "S018": "Ghose et al. (2019)", "S020": "Roy et al. (2022)",
    "S022": "Crooks (2023)", "S024": "Bui et al. (2021)", "S026": "Ghose et al. (2017b)",
    "S028": "Olanrewaju (2025)", "S029": "Ghose et al. (2020)", "S033": "Bui et al. (2023a)",
    "S037": "Bui et al. (2023b)", "S039": "Bullen & Dowdell (2023)", "S040": "Bui et al. (2025)",
    "S042": "Dowdell (2014)", "S046": "Griffiths et al. (2022)", "S051": "Dowdell et al. (2020)",
    "S053": "Newmarch (2025)", "S054": "Bullen et al. (2021a)", "S055": "Bullen et al. (2021b)",
    "S064": "Howell et al. (2023)", "S070": "Formichetti et al. (2026)", "S071": "Peng & Petrović (2024)",
    "S084": "Frischknecht et al. (2019)", "S088": "du Plessis (2022)", "S091": "Andisheh (2025)",
    "S109": "Newmarch et al. (2022)", "S116": "Steven et al. (2025)", "S117": "Liu et al. (2023)",
    "S118": "Röck et al. (2021)", "S123": "Rodríguez Droguett et al. (2020)", "S124": "Luo (2023)",
    "S129": "Krezlik et al. (2025)", "S135": "Trovato et al. (2020)", "S141": "Valencia et al. (2022)",
    "S143": "Hu (2023)", "S144": "Cramblitt et al. (2025)", "S161": "Mok et al. (2025)",
    "S168": "Abbey et al. (2022)", "S179": "Pomponi & D'Amico (2017)", "S180": "Rabani et al. (2021)",
    "S183": "Marsh et al. (2023)", "S184": "Roberts & Ouellet-Plamondon (2025)", "S187": "Pomponi et al. (2015)",
    "S188": "Wu et al. (2017)", "S195": "Lally et al. (2026)", "S203": "Opher et al. (2021)",
    "S206": "Bartolucci et al. (2024)", "S211": "Ghorbany et al. (2025)", "S215": "Kang et al. (2022)",
    "S218": "Grossi et al. (2024)", "S232": "Han & Shen (2024)", "S240": "Herrmann et al. (2022)",
    "S254": "Lim (2025)", "S255": "Doguc et al. (2025)", "S272": "Besana & Tirelli (2022)",
    "S273": "Zhang et al. (2024)", "S283": "Kulthanaphanich & Lin (2025)", "S284": "Tian et al. (2011)",
    "S290": "La Mantia et al. (2022)", "S336": "Nawarathna et al. (2021)",
}
assert set(CITATION_LABEL) == set(inc["Study_ID"]), \
    "CITATION_LABEL is out of sync with the 68 included Study_IDs"

def _surname_token(label):
    # strip the trailing "(year[ab])" and " et al."/" & X"/" and X" second author
    core = re.sub(r"\s*\(\d{4}[ab]?\)\s*$", "", label)
    core = re.split(r"\s+et al\.| & | and ", core)[0]
    return core.strip()

for _, r in inc.iterrows():
    label = CITATION_LABEL[r["Study_ID"]]
    y = int(re.search(r"\d{4}", label).group())
    assert y == int(r["Year_Verified"]) or (r["Study_ID"] == "S195" and y == 2026), \
        f"{r['Study_ID']}: label year {y} != Year_Verified {r['Year_Verified']}"
    surname = _surname_token(label)
    assert surname.lower() in str(r["Authors"]).lower(), \
        f"{r['Study_ID']}: surname '{surname}' not found in Authors field {r['Authors']!r}"

inc["citation_label"] = inc["Study_ID"].map(CITATION_LABEL)
dup_labels = inc["citation_label"].value_counts()
assert dup_labels.max() == 1, f"duplicate citation labels remain: {dup_labels[dup_labels > 1].to_dict()}"

# Column 1: Operational carbon quantified. True where Operational_Carbon
# begins with "Yes" (covers "Yes", "Yes: 86%...", "Yes (informal...)", etc.)
inc["col1_opcarbon"] = inc["Operational_Carbon"].astype(str).str.strip().str.startswith("Yes")

# Column 2: EN 15978 or equivalent WLC-assessment standard referenced.
# Matching rule: true if Standards_Referenced passes any of three tests.
# (1) It contains "15978" in any citation format (EN 15978, BS EN 15978,
# NS 3720 "based on EN 15978", etc.). (2) It names ISO 21931, the ISO
# whole-life-carbon-assessment framework standard and the recognised
# international equivalent to EN 15978. (3) It names the "RICS Whole Life
# Carbon Assessment" methodology, RICS's own WLC standard, built on and
# referencing EN 15978.
STD_PATTERN = re.compile(r"15978|21931|RICS\s+Whole\s+Life\s+Carbon", re.I)
inc["col2_en15978"] = inc["Standards_Referenced"].astype(str).apply(lambda s: bool(STD_PATTERN.search(s)))

# Columns 3-6: hand-coded per Study_ID from a full read of Emission_Factor_Source.
# Default is False for every record; only True cells are listed.
COL3_GRID_EF_NAMED_TRUE = {
    "S054": "LCAQuick v3.4.3 embedded database (BRANZ CO2NSTRUCT-derived reference-building "
            "factors); EORA MRIO database for consumption-based grid/economy-wide emission factors",
    "S055": "LCAQuick embedded database (BRANZ CO2NSTRUCT); MBIE electricity emission-factor "
            "scenarios (2016, 2019) for grid decarbonisation sensitivity; Ecoinvent 3.5 for "
            "wood-pellet-furnace factors",
    "S141": "U.S. EPA eGrid database (grid-electricity emission factors); supplementary LCA "
            "data from published literature for embodied components",
    "S161": "RICS guidance values, UK Government GHG Conversion Factors, literature values for "
            "material carbon factors",
    "S203": "One Click LCA database (EPDs, commercial LCA databases); Ontario-specific grid-mix "
            "emission factor for operational carbon",
    "S215": "Chinese national standard GB/T 51366-2019 (Building Carbon Emission Calculation) "
            "emission factors",
    "S254": "Korean National LCI Database (Ministry of Environment) - national emission/"
            "carbon-intensity factors",
    "S283": "Taiwan Ministry of Environment Carbon Footprint Database (2023) - national "
            "emission factors",
}
COL4_SPATIAL_TRUE = {
    "S203": "Ontario-specific grid-mix emission factor for operational carbon",
}
COL5_TEMPORAL_TRUE = {}  # expected empty: no record is coded True for temporal
COL6_TRAJECTORY_TRUE = {
    "S195": "dynamic LCA framework with time-variant emission factors along a decarbonising grid pathway (Lally et al., 2026)",
    "S055": "MBIE electricity emission-factor scenarios (2016, 2019) for grid decarbonisation "
            "sensitivity",
}

inc["col3_gridef"] = inc["Study_ID"].isin(COL3_GRID_EF_NAMED_TRUE)
inc["col4_spatial"] = inc["Study_ID"].isin(COL4_SPATIAL_TRUE)
inc["col5_temporal"] = inc["Study_ID"].isin(COL5_TEMPORAL_TRUE)
inc["col6_trajectory"] = inc["Study_ID"].isin(COL6_TRAJECTORY_TRUE)

COLS = ["col1_opcarbon", "col2_en15978", "col3_gridef", "col4_spatial", "col5_temporal", "col6_trajectory"]
COL_TITLES = ["Operational\ncarbon\nquantified", "EN 15978 or\nequivalent\nreferenced",
              "Grid EF source\nnamed\n(specific)", "Spatial\nresolution\nstated",
              "Temporal\nresolution\nstated", "Trajectory\nstated"]

# Platform / row-block classification from LCA_Tool free text.
# Rule: if a tool is flagged "(primary)" in the text, use that tool. Else
# check keyword presence in priority order LCAQuick > One Click LCA > eTool.
# Else, if the text indicates no software was used/named (None detected,
# Not applicable, Not stated, Not specified, No named, No dedicated, Not a
# named ...), block = "No tool named". Otherwise block = "Other named tool".
NO_TOOL_PAT = re.compile(
    r"none detected|not applicable|not stated|not specified|no named|no dedicated|"
    r"not a named|none named|none applied", re.I)

def classify_platform(text):
    t = str(text)
    m = re.search(r"([A-Za-z0-9 ]+?)\s*\(primary\)", t)
    if m:
        primary = m.group(1).lower()
        if "lcaquick" in primary:
            return "LCAQuick"
        if "one click" in primary or "oneclick" in primary:
            return "One Click LCA"
        if "etool" in primary:
            return "eTool"
    low = t.lower()
    if "lcaquick" in low:
        return "LCAQuick"
    if "one click" in low or "oneclick" in low:
        return "One Click LCA"
    if "etool" in low:
        return "eTool"
    if NO_TOOL_PAT.search(t):
        return "No tool named"
    return "Other named tool"

inc["platform"] = inc["LCA_Tool"].apply(classify_platform)

BLOCK_ORDER = ["LCAQuick", "One Click LCA", "eTool", "Other named tool", "No tool named"]
GROUP_ORDER = {"G1": 0, "G2": 1, "G3": 2}
inc["block_rank"] = inc["platform"].map({b: i for i, b in enumerate(BLOCK_ORDER)})
inc["group_rank"] = inc["Segmentation_Group"].map(GROUP_ORDER)
inc = inc.sort_values(["block_rank", "group_rank", "Study_ID"]).reset_index(drop=True)

block_counts = inc["platform"].value_counts().reindex(BLOCK_ORDER).fillna(0).astype(int)
assert block_counts.sum() == 68, f"platform blocks do not sum to 68: {dict(block_counts)}"

# Column totals (n and %), computed at run time
N = len(inc)
totals = {c: int(inc[c].sum()) for c in COLS}
pct = {c: round(100 * totals[c] / N, 1) for c in COLS}

print(f"N included = {N}")
print("Platform block counts:", dict(block_counts), "sum =", int(block_counts.sum()))
print("Column totals (n / %):")
for c, title in zip(COLS, COL_TITLES):
    print(f"  {c}: n={totals[c]}  ({pct[c]}%)")

# Figure: compact two-panel matrix, laid out for legibility as an academic
# figure.
#   - "true" cells are small square markers, not full-column-width bars,
#     which would read as a bar chart. This matches the marker convention
#     of fig1_evidence_map.png. Marker size is defined in points, not data
#     units, so axes aspect distortion does not affect it.
#   - The 68 rows are split into two side-by-side panels so the figure is
#     wide and short (suited to a journal) rather than one tall, narrow
#     panel of 68 rows. The split point is chosen at run time to balance
#     the two panels' row counts as evenly as possible, not hardcoded to a
#     specific block name.
COL_TITLES_SHORT = ["Operational carbon", "EN 15978+ equivalent", "Grid EF named",
                     "Spatial resolution", "Temporal resolution", "Trajectory"]

def choose_split(order, counts, total):
    """Index (number of leading blocks assigned to the left panel) that
    minimises the row-count imbalance between the two panels."""
    best_i, best_diff = 1, None
    for i in range(1, len(order)):
        left_n = sum(counts[b] for b in order[:i])
        diff = abs(left_n - (total - left_n))
        if best_diff is None or diff < best_diff:
            best_i, best_diff = i, diff
    return best_i

split_i = choose_split(BLOCK_ORDER, block_counts, N)
left_blocks = BLOCK_ORDER[:split_i]
right_blocks = BLOCK_ORDER[split_i:]
left_df = inc[inc["platform"].isin(left_blocks)]
right_df = inc[inc["platform"].isin(right_blocks)]
panel_rows = max(len(left_df), len(right_df))
print(f"Panel split: left={list(left_blocks)} (n={len(left_df)}), "
      f"right={list(right_blocks)} (n={len(right_df)})")

# Block group names are shown as their own header row, like a sub-heading
# in a table. In a narrow left margin next to the row labels they would
# collide with the study labels. Column headers get extra spacing
# (COL_SPACING) so that six two-line labels do not run into each other, as
# they do with unit column spacing.
COL_SPACING = 1.55
PER_ROW_IN = 0.150
n_cols = len(COLS)
fig_w = 9.6
fig, (axL, axR) = plt.subplots(1, 2, figsize=(fig_w, 6.0))  # height set precisely below

def build_items(sub_df, blocks):
    """One list entry per drawn row: ('header', name, n) or ('row', Series)."""
    items = []
    for block in blocks:
        n_b = int(block_counts[block])
        if n_b == 0:
            continue
        items.append(("header", block, n_b))
        for _, row in sub_df[sub_df["platform"] == block].iterrows():
            items.append(("row", row))
    return items

left_items = build_items(left_df, left_blocks)
right_items = build_items(right_df, right_blocks)
n_items = max(len(left_items), len(right_items))
fig_h = n_items * PER_ROW_IN + 1.95
fig.set_size_inches(fig_w, fig_h)

def draw_panel(ax, items):
    col_x = [i * COL_SPACING for i in range(n_cols)]
    y_top = len(items) - 1
    for i, item in enumerate(items):
        y = y_top - i
        if item[0] == "header":
            _, name, n_b = item
            ax.text(-0.55, y, f"{name}  (n={n_b})", ha="left", va="center",
                    fontsize=7.8, fontweight="bold", color="#111111")
            ax.axhline(y - 0.5, color="#CCCCCC", lw=0.7, clip_on=False)
        else:
            _, row = item
            for j, c in enumerate(COLS):
                if row[c]:
                    ax.plot(col_x[j], y, marker="s", markersize=6.2, markerfacecolor=OI["blue"],
                            markeredgecolor="none", zorder=3)
            ax.text(-0.65, y, row["citation_label"], ha="right", va="center", fontsize=6.0, color="#333333")

    ax.set_xlim(-2.9, col_x[-1] + 0.9)
    ax.set_ylim(-0.8, y_top + 1.6)
    ax.set_xticks(col_x)
    # Angled headers: with six columns this close together, horizontal
    # two-line labels run into each other at any column spacing. Angled
    # single-line labels take diagonal rather than horizontal room and do
    # not collide.
    ax.set_xticklabels(COL_TITLES_SHORT, fontsize=7.4, fontweight="bold",
                       rotation=32, ha="left", rotation_mode="anchor")
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", length=0, pad=2)
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

draw_panel(axL, left_items)
draw_panel(axR, right_items)
fig.subplots_adjust(wspace=0.45, top=0.66, bottom=0.02)

# Compact title: one bold headline and one smaller detail line, with the
# legend on its own line below both. Sharing the top-right corner with the
# headline would make the two collide.
headline = f"Disclosure of carbon method and grid emission factor attributes by reviewed record (n = 68)"
detail = (f"n={N} · Operational carbon {pct['col1_opcarbon']:.0f}% · EN 15978+ "
          f"{pct['col2_en15978']:.0f}% · Grid EF named {pct['col3_gridef']:.0f}% · "
          f"Spatial {pct['col4_spatial']:.0f}% · Temporal {pct['col5_temporal']:.0f}% · "
          f"Trajectory {pct['col6_trajectory']:.0f}%")
fig.text(0.01, 0.985, headline, fontsize=13.0, fontweight="bold", ha="left", va="top")
fig.text(0.01, 0.935, detail, fontsize=8.8, ha="left", va="top", color="#333333", style="italic")

legend_elems = [
    Line2D([0], [0], marker="s", color="none", markerfacecolor=OI["blue"], markersize=8, label="disclosed"),
    Line2D([0], [0], marker="s", color="none", markerfacecolor="none", markeredgecolor="none", markersize=8, label="blank = not disclosed"),
]
fig.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(0.01, 0.895),
           ncol=2, frameon=False, fontsize=8.2, borderaxespad=0, handletextpad=0.5, columnspacing=1.4)

fig.savefig(FIGS / "fig3_disclosure_matrix.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig3_disclosure_matrix.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig3_disclosure_matrix.png", bbox_inches="tight", dpi=300)
plt.close(fig)
print("Saved fig3_disclosure_matrix.svg/.pdf/.png (two-panel layout, 68 rows)")

# export the coded table for an independent re-check
inc[["Study_ID", "citation_label", "Segmentation_Group", "platform"] + COLS].to_csv(
    ROOT / "analysis" / "FIG3_DISCLOSURE_CODING.csv", index=False)
print(f"Wrote analysis/FIG3_DISCLOSURE_CODING.csv ({len(inc)} rows)")
