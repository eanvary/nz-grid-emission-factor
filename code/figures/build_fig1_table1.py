"""
Fig. 1 (evidence map) and Table 1 (magnitude register) for the "Where, when,
and which future" manuscript. Both are built entirely from
analysis/LITERATURE_AXIS_REGISTER.csv: no quantitative literal in this file
is a substantive result; the only numeric literals below are layout
constants (sizes, coordinates, dpi, marker geometry).
"""
import re
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "analysis" / "LITERATURE_AXIS_REGISTER.csv"
FIGS = ROOT / "figures"
TABLES = ROOT / "tables"
FIGS.mkdir(parents=True, exist_ok=True)
TABLES.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL  # noqa: E402

# Journal styling (per journal_palette.py): literature rows = CATEGORICAL[0]
# (deep navy); this-study rows = CATEGORICAL[1] (amber, print-safe, not the
# raw fill amber). White/transparent background, no dark panels.
set_journal_style()
LIT_C, STUDY_C = CATEGORICAL[0], CATEGORICAL[1]
plt.rcParams.update({
    "axes.spines.left": False, "axes.spines.bottom": False,
})

reg = pd.read_csv(REG, keep_default_na=False)
AXES = ["axis_spatial", "axis_temporal", "axis_trajectory"]
AXIS_LABELS = ["Where\n(spatial)", "When\n(temporal)", "Which future\n(trajectory)"]

# Merge to one row per STUDY for the evidence-map matrix (Fig. 1): some
# studies contribute two register rows because they report two distinct
# magnitudes for two DIFFERENT axes (e.g. Li et al. 2023's DA7 row codes
# temporal=quantified/trajectory=absent, its M7 row codes the reverse: the
# study as a whole is quantified on BOTH axes). A naive "keep first" would
# silently drop the second axis's coding, so instead take the most-informative
# state per axis (quantified > discussed > absent) across a study's rows.
# The full, non-deduped register is used for Table 1 and the column counts.
STATE_RANK = {"quantified": 2, "discussed": 1, "absent": 0, "": 0}

def merge_group(g):
    out = g.iloc[0].copy()
    for a in AXES:
        best = max(g[a], key=lambda s: STATE_RANK.get(s, 0))
        out[a] = best
    # keep the factor_basis of whichever row is non-blank (prefer explicit)
    nonblank_basis = g.loc[g["factor_basis"].astype(str).str.strip() != "", "factor_basis"]
    out["factor_basis"] = nonblank_basis.iloc[0] if len(nonblank_basis) else g["factor_basis"].iloc[0]
    return out

studies = reg.groupby(["authors_short", "year"], sort=False, as_index=False).apply(
    merge_group, include_groups=False
).reset_index(drop=True)
# groupby(...).apply with include_groups=False drops the grouping cols; restore them
studies[["authors_short", "year"]] = reg.drop_duplicates(
    subset=["authors_short", "year"], keep="first"
)[["authors_short", "year"]].reset_index(drop=True)

DOMAIN_ORDER = {"building_lca": 0, "power_sector": 1, "ev_transport": 2,
                 "data_centre": 3, "methodology_review": 4}
studies["domain_rank"] = studies["domain"].map(DOMAIN_ORDER).fillna(9)
lit = studies[studies["ref_key"] != "this_study"].sort_values(["domain_rank", "year"])
this_row = studies[studies["ref_key"] == "this_study"]
plot_rows = pd.concat([lit, this_row], ignore_index=True)
n_building_lca_last = (lit["domain"] == "building_lca").sum()  # rule position for the annotation

# Column quantified counts: computed from the FULL register (all rows,
# including the two-row studies), per the brief: "Compute these counts from
# the register at run time; do not write them into the code."
col_counts_all = {a: int((reg[a] == "quantified").sum()) for a in AXES}
# unique-study counts (what the matrix actually shows) for the annotation line
col_counts_studies = {a: int((plot_rows[a] == "quantified").sum()) for a in AXES}

# Domain-restricted check (prior literature only, building_lca domain, this_study excluded)
# Used only to compose the title text, not written into the figure as a
# separate hardcoded number; every value below is read from `plot_rows`.
prior_bldg = lit[lit["domain"] == "building_lca"]
bldg_quant = {a: int((prior_bldg[a] == "quantified").sum()) for a in AXES}
bldg_n = len(prior_bldg)

# Figure 1: evidence map
n = len(plot_rows)

# Build explicit y-slots top-down, inserting a one-unit gap after the
# building_lca block (where the annotation line sits) and another before
# this_study (on top of the separator rule already required by the brief) so
# neither the annotation nor the rule collides with a row.
GAP_AFTER_BLDG = 1.0
GAP_BEFORE_THIS_STUDY = 1.0
y_lit = []
cursor = 0.0
for i in range(len(lit)):
    y_lit.append(cursor)
    cursor += 1.0
    if i == n_building_lca_last - 1:
        cursor += GAP_AFTER_BLDG
annot_y_raw = y_lit[n_building_lca_last - 1] + (GAP_AFTER_BLDG + 1.0) / 2.0  # midpoint of the gap
cursor += GAP_BEFORE_THIS_STUDY
y_this = cursor
y_raw = np.array(y_lit + [y_this])
y_positions = y_raw.max() - y_raw  # flip so building_lca (earliest) is at the TOP
annot_y = y_raw.max() - annot_y_raw

fig_h = max(3.2, 0.34 * (y_positions.max() + 1) + 1.6)
fig, ax = plt.subplots(figsize=(8.6, fig_h))

x_cols = [0, 1, 2]

MARKER_FOR_BASIS = {"average": "o", "marginal": "^", "both": "s", "": "o"}
MARKER_SIZE = {"o": 9, "^": 10, "s": 8}
FILL_MAP = {"quantified": True, "discussed": False, "absent": None}

# Flag 2: a "quantified" cell means this study's magnitude for that axis was
# extracted into the register. Whether that specific number was itself
# checked against the primary source (vs. only the compass-scan secondary
# summary) is a separate fact -- magnitude_verified, from the FULL
# (non-merged) register, keyed per (study, axis) via magnitude_axis. Cells
# with no tracked magnitude_value for that axis carry no verification claim
# and are drawn at full weight (nothing in Table 1 to be unverified about).
AXIS_SUFFIX = {"axis_spatial": "spatial", "axis_temporal": "temporal", "axis_trajectory": "trajectory"}
mag_rows = reg[reg["magnitude_value"].astype(str).str.strip() != ""]
verified_lookup = {
    (r["authors_short"], r["year"], r["magnitude_axis"]): r["magnitude_verified"]
    for _, r in mag_rows.iterrows()
}

def draw_marker(ax, x, y, shape, filled, color, verified=True):
    face = color if filled else "none"
    alpha = 1.0 if verified else 0.32
    ax.plot([x], [y], marker=shape, markersize=MARKER_SIZE[shape],
             markerfacecolor=face, markeredgecolor=color, markeredgewidth=1.4,
             alpha=alpha, linestyle="none", zorder=3, clip_on=False)

for i, (_, row) in enumerate(plot_rows.iterrows()):
    y = y_positions[i]
    is_this_study = row["ref_key"] == "this_study"
    marker_color = STUDY_C if is_this_study else LIT_C
    shape = MARKER_FOR_BASIS.get(row["factor_basis"], "o")
    for xc, a in zip(x_cols, AXES):
        state = row[a]
        filled = FILL_MAP.get(state, None)
        if filled is None:
            continue  # absent -> empty cell
        mag_verified = verified_lookup.get((row["authors_short"], row["year"], AXIS_SUFFIX[a]))
        verified = mag_verified != "no"  # None (no tracked magnitude) or "yes" -> full weight
        draw_marker(ax, xc, y, shape, filled, marker_color, verified=verified)
    # left margin: authors + year
    ax.text(-0.55, y, f"{row['authors_short']} ({row['year']})", ha="right", va="center",
             fontsize=7.6, fontweight="bold" if is_this_study else "normal",
             color=STUDY_C if is_this_study else "#222222")
    # right margin: grid system
    ax.text(2.55, y, row["grid_system"], ha="left", va="center", fontsize=7.0, color="#777777")

# separator rule above this_study row, in the dedicated gap
sep_y = (y_positions[-1] + y_positions[-2]) / 2.0
ax.axhline(sep_y, color="#444444", lw=0.9, xmin=-0.02, xmax=1.02, clip_on=False)

ax.set_xlim(-0.6, 5.6)
ax.set_ylim(y_positions.min() - 0.7, y_positions.max() + 0.7)
ax.set_xticks(x_cols)
ax.set_xticklabels(AXIS_LABELS, fontsize=9.5, fontweight="bold")
ax.xaxis.tick_top()
ax.set_yticks([])

# legend: fill = coding, shape = factor basis -- outside axes, right-anchored
legend_elems = [
    Line2D([0], [0], marker="o", color="none", markerfacecolor=LIT_C, markeredgecolor=LIT_C,
           markersize=9, label="quantified"),
    Line2D([0], [0], marker="o", color="none", markerfacecolor="none", markeredgecolor=LIT_C,
           markersize=9, label="discussed, not quantified"),
    Line2D([0], [0], marker="o", color="none", markerfacecolor=LIT_C, markeredgecolor=LIT_C,
           markersize=9, alpha=0.32, label="quantified, magnitude not verified vs. primary source"),
    Line2D([0], [0], marker="", color="none", label="(empty = not addressed)"),
    Line2D([0], [0], marker="o", color="none", markerfacecolor=LIT_C, markeredgecolor=LIT_C,
           markersize=9, label="average factor"),
    Line2D([0], [0], marker="^", color="none", markerfacecolor=LIT_C, markeredgecolor=LIT_C,
           markersize=9, label="marginal factor"),
    Line2D([0], [0], marker="s", color="none", markerfacecolor=LIT_C, markeredgecolor=LIT_C,
           markersize=8, label="both average & marginal"),
    Line2D([0], [0], marker="o", color="none", markerfacecolor=STUDY_C, markeredgecolor=STUDY_C,
           markersize=9, label="this study"),
]
ax.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(1.02, 1.0),
          frameon=False, fontsize=7.6, borderaxespad=0)

# annotation line: quantified-cell counts per column, computed at run time.
# Sits in the dedicated gap right after the last building-LCA row, to the
# right of the spatial (x=0) column, so it cannot overlap any marker row.
annot = (f"Quantified cells in this map: Where = {col_counts_studies['axis_spatial']}, "
         f"When = {col_counts_studies['axis_temporal']}, "
         f"Which future = {col_counts_studies['axis_trajectory']} "
         f"(of {n} studies incl. this one; "
         f"{len(reg)} register rows incl. {len(reg) - len(studies)} studies with two reported magnitudes).")
ax.text(0.15, annot_y, annot,
        fontsize=7.2, color="#333333", style="italic", ha="left", va="center")

# title: compose the pattern from the counts actually computed above
if bldg_quant["axis_spatial"] == 0 and col_counts_studies["axis_spatial"] > col_counts_studies["axis_trajectory"]:
    title = (f"Spatial evidence exists ({col_counts_studies['axis_spatial']} studies) — but "
             f"almost none of it is building-LCA:\n"
             f"within building LCA, spatial resolution is quantified in "
             f"{bldg_quant['axis_spatial']}/{bldg_n} prior studies vs. temporal in "
             f"{bldg_quant['axis_temporal']}/{bldg_n}")
else:
    title = (f"Quantified evidence by axis: Where={col_counts_studies['axis_spatial']}, "
             f"When={col_counts_studies['axis_temporal']}, "
             f"Which future={col_counts_studies['axis_trajectory']}")
ax.set_title(title, fontsize=11.5, loc="left", fontweight="bold", pad=14)

fig.savefig(FIGS / "fig1_evidence_map.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig1_evidence_map.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig1_evidence_map.png", bbox_inches="tight", dpi=300)
plt.close(fig)
print(f"Saved fig1_evidence_map.svg/.pdf/.png ({n} rows plotted, {len(reg)} register rows total)")
print(f"Column quantified counts (unique studies plotted): {col_counts_studies}")
print(f"Column quantified counts (all register rows):      {col_counts_all}")
print(f"Building-LCA-only prior-literature quantified counts (n={bldg_n}): {bldg_quant}")

# Flag 2 self-audit: magnitude_verified counts (rows that assert a magnitude
# only -- rows with no magnitude_value have nothing to verify and are excluded
# from this count, same convention as the CSV's own "n/a" value).
n_yes = int((mag_rows["magnitude_verified"] == "yes").sum())
n_no = int((mag_rows["magnitude_verified"] == "no").sum())
pct_verified = 100 * n_yes / (n_yes + n_no) if (n_yes + n_no) else 0
print(f"\n=== Flag 2 self-audit: magnitude verification ===")
print(f"Magnitude rows: {n_yes + n_no} (of {len(reg)} register rows, "
      f"{len(reg) - len(mag_rows)} carry no magnitude_value)")
print(f"magnitude_verified: yes={n_yes}, no={n_no} ({pct_verified:.1f}% verified)")
if pct_verified < 50:
    print(f"*** FEWER THAN HALF THE MAGNITUDE ROWS ARE VERIFIED ({pct_verified:.1f}%) ***")
print("'no' rows:")
for _, r in mag_rows[mag_rows["magnitude_verified"] == "no"].iterrows():
    print(f"  {r['ref_key']} ({r['authors_short']} {r['year']}, {r['magnitude_axis']}): \"{r['magnitude_value']}\"")

# Table 1: magnitude register
tbl = reg[reg["magnitude_value"].astype(str).str.strip() != ""].copy()

AXIS_TITLE_ORDER = {"spatial": 0, "temporal": 1, "trajectory": 2}
tbl["axis_rank"] = tbl["magnitude_axis"].map(AXIS_TITLE_ORDER)

def lead_abs_value(s):
    m = re.search(r"[-+]?\d+(\.\d+)?", str(s))
    return abs(float(m.group())) if m else np.nan

tbl["lead_abs"] = tbl["magnitude_value"].apply(lead_abs_value)
tbl["study_label"] = tbl["authors_short"] + " (" + tbl["year"].astype(str) + ")"
tbl = tbl.sort_values(["axis_rank", "lead_abs", "study_label"],
                       ascending=[True, False, True], na_position="last")

out = pd.DataFrame({
    "Study": tbl["study_label"],
    "Grid system": tbl["grid_system"],
    "Axis": tbl["magnitude_axis"].str.capitalize(),
    "Factor basis": tbl["factor_basis"].replace("", "not stated"),
    "Reported magnitude": tbl["magnitude_value"],
    "Spatial boundary applied": tbl["spatial_boundary_used"].replace("", "n/a"),
    "Magnitude verified": tbl["magnitude_verified"].map({"yes": "Yes", "no": "No"}).fillna(tbl["magnitude_verified"]),
})

# word-count guard (Step 3: keep every cell under twelve words)
max_words = out.astype(str).map(lambda s: len(s.split())).max().max()
print(f"Max words in any Table 1 cell: {max_words} (must be <12)")

out.to_csv(TABLES / "table1_reported_magnitudes.csv", index=False)

md_lines = ["| " + " | ".join(out.columns) + " |",
            "|" + "|".join(["---"] * len(out.columns)) + "|"]
for _, r in out.iterrows():
    md_lines.append("| " + " | ".join(str(v) for v in r.values) + " |")
(TABLES / "table1_reported_magnitudes.md").write_text("\n".join(md_lines), encoding="utf-8")

print(f"Wrote table1_reported_magnitudes.csv/.md ({len(out)} rows)")
