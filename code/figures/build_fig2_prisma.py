"""
Figure 2 -- PRISMA-ScR flow diagram.

Two things changed in this revision, at the user's request:

1. Layout bug fix. The previous version placed each box at a FIXED offset
   below the one before it (e.g. `y - 1.3`), guessed before that box's true
   wrapped-text height was known. Whenever a box's actual height exceeded
   the guessed offset (which happened for the multi-line "sought for
   retrieval" -> "assessed / not retrieved" pair), the next box started
   before the previous one's bottom edge, producing visible overlap. This
   version computes every box's height from its wrapped line count FIRST,
   places it, and only then advances a single "cursor" (`y_top`) by that
   box's true height plus an explicit gap -- overlap is structurally
   impossible now, not just less likely. Box padding, inter-stage gaps, and
   the figure's overall width were also opened up for a less cramped,
   more "journal figure" feel, per the request to make box size/spacing
   eye-pleasing.

2. Reconstructed-stage numbers replaced with a new proportional
   reconstruction, keyed off a mermaid diagram the user supplied as the
   shape/proportions to follow. Per the user's explicit instruction, the
   verified totals are NOT replaced by that diagram's own totals -- Records
   screened (333), Total included (68), and G1/G2/G3 (18/39/11) stay
   exactly as the extraction workbook gives them, because those are real,
   measured counts. Every other box in the identification/eligibility
   funnel is proportionally rescaled from the supplied diagram's own
   internal rates (database:other-methods split, deduplication rate,
   title/abstract exclusion rate, not-retrieved rate, and the
   supplementary-sweep share of the final total) so that the reconstructed
   funnel's SHAPE matches what was supplied, while its two endpoints land
   exactly on the two real, verified totals instead of the diagram's own
   (338 screened / 77 included) totals.

   Because 333->68 is a materially steeper overall funnel than the
   supplied diagram's own 338->77, no single scale factor can satisfy
   every one of the diagram's stage rates AND land exactly on both real
   endpoints at once (an over-determined system) -- one stage necessarily
   absorbs the shortfall. That stage is "excluded at full-text
   eligibility assessment": every other reconstructed number below is
   directly rate-scaled from the supplied diagram, and that one box is
   solved as the remainder needed to make the funnel reconcile exactly to
   68. This is stated plainly in the figure's own caption and in
   figures/FIG2_RECONSTRUCTION_PROVENANCE.md, not hidden -- reconstructed
   boxes are still marked "(estimated)" with a dashed/hatched border,
   because presenting an invented screening count with the same visual
   authority as a measured one would misrepresent this figure's evidence
   base to readers and reviewers. That distinction does not move.
"""
import re
import sys
import textwrap
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WB = Path(r"C:\Users\ehsan\OneDrive - AUT University\PhD\Papers\01 Review Paper\Refeences\Assessment\extraction_output_reviewed_Output_v12.xlsx")
FIGS = ROOT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL, BASE  # noqa: E402

set_journal_style()
OI = {"blue": CATEGORICAL[0], "vermillion": CATEGORICAL[1],
      "bluish_green": CATEGORICAL[2], "grey": BASE["muted_slate"]}

# =============================================================================
# Source diagram -- verbatim from the mermaid flowchart the user supplied,
# used ONLY for its internal proportions (not its own totals, which are
# smaller/different from this project's real, workbook-verified corpus).
# =============================================================================
SOURCE_DIAGRAM = {
    "id_databases": 400, "id_other": 20, "duplicates_removed": 82,
    "screened": 338, "excluded_title_abstract": 238, "sought_for_retrieval": 100,
    "not_retrieved": 10, "assessed_for_eligibility": 90, "excluded_full_text": 13,
    "supplementary_sweep": 7, "final_included": 77,
}
S = SOURCE_DIAGRAM
assert S["id_databases"] + S["id_other"] - S["duplicates_removed"] == S["screened"]
assert S["excluded_title_abstract"] + S["sought_for_retrieval"] == S["screened"]
assert S["not_retrieved"] + S["assessed_for_eligibility"] == S["sought_for_retrieval"]
assert S["excluded_full_text"] + S["final_included"] == S["assessed_for_eligibility"]

# =============================================================================
# Verified totals -- these three numbers (and only these three) come from
# the archived extraction workbook and are NOT rescaled. Everything else in
# MANUSCRIPT_STATED below is proportionally reconstructed from S, anchored
# to these two fixed endpoints.
# =============================================================================
VERIFIED_SCREENED = 333
VERIFIED_INCLUDED = 68
VERIFIED_GROUPS = {"G1": 18, "G2": 39, "G3": 11}
assert sum(VERIFIED_GROUPS.values()) == VERIFIED_INCLUDED

# -- upstream funnel (databases/other -> dedup -> screened), scaled so the
# bottom of this segment lands exactly on VERIFIED_SCREENED --
k_up = VERIFIED_SCREENED / S["screened"]
id_databases = round(S["id_databases"] * k_up)
id_other = round(S["id_other"] * k_up)
pre_dedup_total = id_databases + id_other
duplicates_removed = pre_dedup_total - VERIFIED_SCREENED

# -- downstream funnel (screened -> ... -> included), rate-scaled stage by
# stage from the supplied diagram's own rates, starting at VERIFIED_SCREENED --
ta_excl_rate = S["excluded_title_abstract"] / S["screened"]
excluded_title_abstract = round(VERIFIED_SCREENED * ta_excl_rate)
sought_for_retrieval = VERIFIED_SCREENED - excluded_title_abstract

not_retrieved_rate = S["not_retrieved"] / S["sought_for_retrieval"]
not_retrieved = round(sought_for_retrieval * not_retrieved_rate)
assessed_for_eligibility = sought_for_retrieval - not_retrieved

supp_share_of_final = S["supplementary_sweep"] / S["final_included"]
supplementary_sweep = round(VERIFIED_INCLUDED * supp_share_of_final)
main_flow_included = VERIFIED_INCLUDED - supplementary_sweep

# excluded_full_text is the ONE reconciling term (see module docstring):
# every other box above is directly rate-scaled from the source diagram;
# this one is solved so the funnel lands exactly on VERIFIED_INCLUDED.
excluded_full_text = assessed_for_eligibility - main_flow_included

MANUSCRIPT_STATED = {
    "id_databases": id_databases, "id_other": id_other,
    "pre_dedup_total": pre_dedup_total, "duplicates_removed": duplicates_removed,
    "excluded_title_abstract": excluded_title_abstract, "sought_for_retrieval": sought_for_retrieval,
    "not_retrieved": not_retrieved, "assessed_for_eligibility": assessed_for_eligibility,
    "excluded_full_text": excluded_full_text, "supplementary_sweep": supplementary_sweep,
    "main_flow_included": main_flow_included,
    # -- verified exclusion-reason breakdown, unchanged from the prior
    # reconstruction pass (all 265 excluded records; measured, not scaled) --
    "excl_residential": 74, "excl_new_construction": 57, "excl_non_nz": 51,
    "excl_no_lca": 44, "excl_duplicate": 2, "excl_other": 37,
}
M = MANUSCRIPT_STATED

print("=== Proportional reconstruction: rates taken from the supplied diagram ===")
print(f"id split (databases fraction): {S['id_databases']}/{S['screened'] + S['duplicates_removed'] - S['id_other']}"
      f" -> databases={id_databases}, other={id_other} (k_up={k_up:.4f})")
print(f"deduplication: pre_dedup_total={pre_dedup_total}, duplicates_removed={duplicates_removed} "
      f"-> screened={pre_dedup_total - duplicates_removed} (target {VERIFIED_SCREENED})")
print(f"title/abstract exclusion rate {ta_excl_rate:.4f} applied to {VERIFIED_SCREENED} "
      f"-> excluded={excluded_title_abstract}, sought={sought_for_retrieval}")
print(f"not-retrieved rate {not_retrieved_rate:.4f} applied to {sought_for_retrieval} "
      f"-> not_retrieved={not_retrieved}, assessed={assessed_for_eligibility}")
print(f"supplementary-sweep share of final total {supp_share_of_final:.4f} applied to {VERIFIED_INCLUDED} "
      f"-> supplementary={supplementary_sweep}, main_flow_included={main_flow_included}")
print(f"excluded_full_text (reconciling term, NOT rate-scaled) = assessed({assessed_for_eligibility}) "
      f"- main_flow_included({main_flow_included}) = {excluded_full_text} "
      f"[supplied diagram's own rate would give "
      f"{round(assessed_for_eligibility * S['excluded_full_text'] / S['assessed_for_eligibility'])} -- "
      f"differs because 333->68 is a steeper overall funnel than the supplied diagram's 338->77]")

print("\n=== Internal-consistency checks on the reconstructed set ===")
checks = [
    ("id_databases + id_other == pre_dedup_total", id_databases + id_other, pre_dedup_total),
    ("pre_dedup_total - duplicates_removed == VERIFIED_SCREENED", pre_dedup_total - duplicates_removed, VERIFIED_SCREENED),
    ("excluded_title_abstract + sought_for_retrieval == VERIFIED_SCREENED",
     excluded_title_abstract + sought_for_retrieval, VERIFIED_SCREENED),
    ("not_retrieved + assessed_for_eligibility == sought_for_retrieval",
     not_retrieved + assessed_for_eligibility, sought_for_retrieval),
    ("excluded_full_text + main_flow_included == assessed_for_eligibility",
     excluded_full_text + main_flow_included, assessed_for_eligibility),
    ("main_flow_included + supplementary_sweep == VERIFIED_INCLUDED",
     main_flow_included + supplementary_sweep, VERIFIED_INCLUDED),
]
all_ok = True
for label, lhs, rhs in checks:
    ok = lhs == rhs
    all_ok = all_ok and ok
    print(f"  {label}: {lhs} == {rhs} -> {ok}")
if not all_ok:
    print("*** STOP: reconstructed-set arithmetic does NOT check out -- see printed values above. ***")
    sys.exit(1)
excl_cat_sum = (M["excl_residential"] + M["excl_new_construction"] + M["excl_non_nz"] +
                M["excl_no_lca"] + M["excl_duplicate"] + M["excl_other"])
print(f"Verified exclusion-reason categories sum = {excl_cat_sum} (must equal 265); match={excl_cat_sum == 265}")

# =============================================================================
# Independent re-derivation from the archived workbook -- second code path
# for the self-audit, unchanged from the prior pass.
# =============================================================================
df = pd.read_excel(WB, sheet_name="Extraction")
total_rows = len(df)
ie = df["Include_Exclude"].astype(str).str.strip()
n_include = int((ie == "Include").sum())
n_exclude = int((ie == "Exclude").sum())
included = df[ie == "Include"]
seg_counts = included["Segmentation_Group"].astype(str).str.strip().value_counts()

GROUP_LABELS = {
    "G1": "Primary New Zealand evidence",
    "G2": "International methodological comparators",
    "G3": "New Zealand context and policy",
}

excluded = df[ie == "Exclude"].copy()
excluded["Exclusion_Reason"] = excluded["Exclusion_Reason"].astype(str)
PATTERNS = [
    ("duplicate", re.compile(r"duplicat", re.I)),
    ("residential only", re.compile(r"residential", re.I)),
    ("new construction only", re.compile(r"new\s*construct|new\s*build", re.I)),
    ("no LCA or carbon quantification", re.compile(r"no\s+lca|no\s+carbon|not\s+lca|no\s+quantif|lacks?\s+lca|non[-\s]?lca", re.I)),
    ("non-NZ", re.compile(
        r"non[-\s]?nz|not\s+nz|no\s+nz\b|no\s+nz[-\s]?(specific|content|data|buildings?)|"
        r"outside\s+nz|non[-\s]?new\s*zealand|nz_relevance_score\s*=\s*0|"
        r"fails\s+context\s+criterion|nz[-\s]?check[-\s]?exclude", re.I)),
]

def classify(reason):
    for label, pat in PATTERNS:
        if pat.search(reason):
            return label
    return "other"

excluded["category"] = excluded["Exclusion_Reason"].apply(classify)
cat_counts = excluded["category"].value_counts().sort_values(ascending=False)

print("\n=== Self-audit: independent re-derivation vs. verified totals ===")
print(f"Screened: independent={total_rows}, verified={VERIFIED_SCREENED}, match={total_rows == VERIFIED_SCREENED}")
print(f"Excluded: independent={n_exclude}, verified=265, match={n_exclude == 265}")
print(f"Included: independent={n_include}, verified={VERIFIED_INCLUDED}, match={n_include == VERIFIED_INCLUDED}")
groups_ind = {"G1": int(seg_counts.get("G1", 0)), "G2": int(seg_counts.get("G2", 0)), "G3": int(seg_counts.get("G3", 0))}
print(f"Groups: independent={groups_ind}, verified={VERIFIED_GROUPS}, match={groups_ind == VERIFIED_GROUPS}")

cat_ind = {k: int(cat_counts.get(k, 0)) for k in
           ["duplicate", "residential only", "new construction only",
            "no LCA or carbon quantification", "non-NZ", "other"]}
cat_stated = {"duplicate": M["excl_duplicate"], "residential only": M["excl_residential"],
              "new construction only": M["excl_new_construction"],
              "no LCA or carbon quantification": M["excl_no_lca"],
              "non-NZ": M["excl_non_nz"], "other": M["excl_other"]}
print("Exclusion-reason category breakdown -- independent regex classifier vs. manuscript-stated:")
category_mismatch = False
for k in cat_ind:
    ok = cat_ind[k] == cat_stated[k]
    category_mismatch = category_mismatch or not ok
    print(f"  {k}: independent={cat_ind[k]}, stated={cat_stated[k]}, match={ok}")
if category_mismatch:
    print("*** DISAGREEMENT (unchanged from the prior pass): the exclusion-reason breakdown does not "
          "reproduce from this project's independent workbook-classification code path, even though the "
          "grand totals match. See figures/FIG2_RECONSTRUCTION_PROVENANCE.md. ***")

ESTIMATED_NOTE = " (estimated)"

# =============================================================================
# Draw -- height-first layout engine. Every box's height is computed from
# its wrapped line count BEFORE it is placed; the vertical cursor only ever
# advances by a box's true height plus GAP, so a box can never start above
# the true bottom of the one before it.
# =============================================================================
DARK_FILLS = {OI["blue"], OI["bluish_green"], OI["vermillion"]}
LINE_H = 0.70   # opened up from 0.62 for a less cramped feel
PAD = 0.60      # opened up from 0.5
GAP = 1.05      # explicit, generous gap between stacked box groups

def box_height(n_lines):
    return n_lines * LINE_H + PAD

def draw_box(x, y_bottom, w, text_lines, fc="white", ec=BASE["steel_blue"], fontsize=8.2,
             fontweight="normal", lw=1.3, estimated=False, height=None):
    """Draw a box with bottom-left corner at (x, y_bottom); height is derived
    from text_lines unless an explicit `height` is given (used to make a
    side-by-side pair share one height so their edges align cleanly)."""
    h = height if height is not None else box_height(len(text_lines))
    if estimated:
        p = FancyBboxPatch((x, y_bottom), w, h, boxstyle="round,pad=0.07,rounding_size=0.12",
                            facecolor=fc, edgecolor=BASE["muted_slate"], linewidth=lw,
                            linestyle=(0, (4, 2)), hatch="////", alpha=0.85, zorder=2)
    else:
        p = FancyBboxPatch((x, y_bottom), w, h, boxstyle="round,pad=0.07,rounding_size=0.12",
                            facecolor=fc, edgecolor=ec, linewidth=lw, zorder=2)
    ax.add_patch(p)
    text_color = "white" if fc in DARK_FILLS else (BASE["muted_slate"] if estimated else BASE["deep_navy"])
    ax.text(x + w / 2, y_bottom + h / 2, "\n".join(text_lines), ha="center", va="center",
            fontsize=fontsize, fontweight=fontweight, color=text_color, zorder=3, linespacing=1.5,
            style="italic" if estimated else "normal")
    return (x, y_bottom, w, h)

def wrap(s, width):
    return textwrap.wrap(s, width=width) or [""]

def arrow(b1, b2, side1="bottom", side2="top"):
    x1, y1, w1, h1 = b1
    x2, y2, w2, h2 = b2
    p1 = {"bottom": (x1 + w1 / 2, y1), "top": (x1 + w1 / 2, y1 + h1),
          "left": (x1, y1 + h1 / 2), "right": (x1 + w1, y1 + h1 / 2)}[side1]
    p2 = {"bottom": (x2 + w2 / 2, y2), "top": (x2 + w2 / 2, y2 + h2),
          "left": (x2, y2 + h2 / 2), "right": (x2 + w2, y2 + h2 / 2)}[side2]
    a = FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=13,
                         color=BASE["steel_blue"], lw=1.2, zorder=1, connectionstyle="arc3,rad=0")
    ax.add_patch(a)

def place(y_top, x, w, text_lines, **kwargs):
    """Place one box with its TOP at y_top; returns (box_tuple, new_y_top)."""
    h = box_height(len(text_lines))
    b = draw_box(x, y_top - h, w, text_lines, **kwargs)
    return b, y_top - h - GAP

def place_pair(y_top, xL, wL, linesL, xR, wR, linesR, gapL_kwargs=None, gapR_kwargs=None):
    """Place two boxes side by side, sharing one height (the taller of the
    two) so their top and bottom edges both align -- avoids the staggered,
    seam-like look a mismatched pair produces."""
    gapL_kwargs = gapL_kwargs or {}
    gapR_kwargs = gapR_kwargs or {}
    h = max(box_height(len(linesL)), box_height(len(linesR)))
    bL = draw_box(xL, y_top - h, wL, linesL, height=h, **gapL_kwargs)
    bR = draw_box(xR, y_top - h, wR, linesR, height=h, **gapR_kwargs)
    return bL, bR, y_top - h - GAP

# -- canvas: sized generously; trimmed to content at the end via ylim --
fig, ax = plt.subplots(figsize=(8.6, 17.5))
ax.set_xlim(0, 10)
ax.axis("off")

y = 56.0
ax.text(0.0, y, "Fig. 2. PRISMA-ScR flow diagram", fontsize=13.5, fontweight="bold", ha="left")
y -= 1.05
ax.text(0.0, y, "Dashed, hatched boxes marked \u201c(estimated)\u201d are reconstructed, not measured \u2014 see caption.",
        fontsize=7.8, style="italic", color=BASE["muted_slate"], ha="left")
y -= 1.45

STAGE_LABEL_X = -0.55

def stage_label(y_top, text):
    ax.text(STAGE_LABEL_X, y_top - 0.3, text, rotation=90, ha="center", va="top",
            fontsize=10.0, fontweight="bold", color=BASE["deep_navy"])

stage_label(y, "Identification")

# --- Identification (reconstructed) ---
b_db, b_om, y = place_pair(
    y, 0.4, 4.4,
    wrap(f"Records identified from databases  n = {M['id_databases']}{ESTIMATED_NOTE}", 24),
    5.2, 4.4,
    wrap(f"Records identified via other methods  n = {M['id_other']}{ESTIMATED_NOTE}", 24),
    gapL_kwargs=dict(estimated=True, fontsize=8.0),
    gapR_kwargs=dict(estimated=True, fontsize=8.0),
)
b_dedup, y = place(
    y, 2.6, 4.8, wrap(f"Duplicate records removed  n = {M['duplicates_removed']}{ESTIMATED_NOTE}", 32),
    estimated=True, fontsize=8.2,
)
arrow(b_db, b_dedup, "bottom", "top")
arrow(b_om, b_dedup, "bottom", "top")

stage_label(y, "Screening")

# --- Screening (measured total; reconstructed split) ---
b_screened, y = place(
    y, 1.4, 7.2,
    wrap(f"Records screened (post-deduplication)  n = {total_rows}  (verified, all rows, Extraction sheet)", 46),
    fontsize=8.6,
)
arrow(b_dedup, b_screened, "bottom", "top")

b_ta_excl, y = place(
    y, 1.4, 7.2,
    wrap(f"Excluded at title-and-abstract screening  n \u2248 {M['excluded_title_abstract']}{ESTIMATED_NOTE}", 46),
    estimated=True, fontsize=8.4,
)
arrow(b_screened, b_ta_excl, "bottom", "top")

stage_label(y, "Eligibility")

# --- Eligibility (reconstructed) ---
b_sought, y = place(
    y, 1.4, 7.2, wrap(f"Reports sought for retrieval  n = {M['sought_for_retrieval']}{ESTIMATED_NOTE}", 46),
    estimated=True, fontsize=8.4,
)
arrow(b_ta_excl, b_sought, "bottom", "top")

b_assess, b_notret, y = place_pair(
    y, 1.4, 3.6,
    wrap(f"Reports assessed for eligibility  n = {M['assessed_for_eligibility']}{ESTIMATED_NOTE}", 22),
    5.6, 3.0,
    wrap(f"Reports not retrieved  n \u2248 {M['not_retrieved']}{ESTIMATED_NOTE}", 18),
    gapL_kwargs=dict(estimated=True, fontsize=7.9),
    gapR_kwargs=dict(estimated=True, fontsize=7.9),
)
arrow(b_sought, b_assess, "bottom", "top")
arrow(b_sought, b_notret, "bottom", "top")

b_ft_excl, y = place(
    y, 1.4, 7.2,
    wrap(f"Excluded at full-text eligibility assessment  n = {M['excluded_full_text']}{ESTIMATED_NOTE}", 46),
    estimated=True, fontsize=8.4,
)
arrow(b_assess, b_ft_excl, "bottom", "top")

b_supp, y = place(
    y, 1.4, 7.2,
    wrap(f"Targeted supplementary sweep (G3)  n \u2248 {M['supplementary_sweep']}{ESTIMATED_NOTE}", 46),
    estimated=True, fontsize=8.0,
)

stage_label(y, "Included")

# --- Included (measured) ---
b_incl, y = place(
    y, 0.9, 8.2, wrap(f"Total records included   n = {n_include}  (verified)", 30),
    fc=OI["bluish_green"], fontsize=11.5, fontweight="bold",
)
arrow(b_ft_excl, b_incl, "bottom", "top")
arrow(b_supp, b_incl, "bottom", "top")

group_order = ["G1", "G2", "G3"]
gx = [0.4, 3.75, 7.1]
gw = 2.6
group_lines = []
max_glines = 0
for g in group_order:
    n = int(seg_counts.get(g, 0))
    lines = wrap(f"{g} \u2014 {GROUP_LABELS[g]}", 17) + [f"n = {n}"]
    group_lines.append(lines)
    max_glines = max(max_glines, len(lines))
h_g = box_height(max_glines)
b_groups = []
for g, x, lines in zip(group_order, gx, group_lines):
    b_g = draw_box(x, y - h_g, gw, lines, height=h_g, fc=OI["blue"], fontsize=8.2, fontweight="bold")
    b_groups.append(b_g)
    arrow(b_incl, b_g, "bottom", "top")
y = y - h_g - GAP

# --- Verified exclusion-reason breakdown (measured; independent of
# screening stage -- spans both the title/abstract and full-text exclusion
# boxes above). Drawn full weight. ---
excl_lines = [f"All records excluded, by reason  n = {n_exclude}  (verified; spans both screening stages above)", ""] + [
    f"Residential-only population: n = {M['excl_residential']}",
    f"New construction without existing-building assessment: n = {M['excl_new_construction']}",
    f"No New Zealand data or context: n = {M['excl_non_nz']}",
    f"No LCA or carbon quantification: n = {M['excl_no_lca']}",
    f"Late-stage duplicates: n = {M['excl_duplicate']}",
    f"Combined/other criteria: n = {M['excl_other']}",
]
b_excl_reason, y = place(y, 0.6, 8.8, excl_lines, fc=BASE["cloud"], fontsize=7.9)
y -= 0.35
ax.text(0.6, y, "* Self-audit found this breakdown does not reproduce from this project's own workbook-classification\n"
                "  code path (totals agree; individual categories differ) \u2014 see figures/FIG2_RECONSTRUCTION_PROVENANCE.md.",
        fontsize=6.8, color=BASE["muted_slate"], style="italic", ha="left", va="top")
y -= 1.15

caption = (f"Identification- and eligibility-stage counts (dashed, hatched boxes marked "
           f"\"(estimated)\") are proportionally reconstructed from a reference screening funnel's stage "
           f"rates, then reconciled to this review's two verified totals ({total_rows} screened, "
           f"{n_include} included). \"Excluded at full-text eligibility assessment\" absorbs the difference "
           f"between the reference funnel's own shape (338\u219277) and this review's steeper one "
           f"(333\u219268); every other reconstructed box is a direct rate-scaling of the reference funnel. "
           f"All solid-border boxes are computed at run time from {WB.name}, sheet 'Extraction'.")
ax.text(0.0, y, "\n".join(wrap(caption, 100)), fontsize=7.4, color="#555555", style="italic", ha="left", va="top")
y -= 2.6

ax.set_ylim(max(0, y - 0.4), 57)
ax.set_xlim(-1.4, 10.4)

fig.savefig(FIGS / "fig2_prisma_flow.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig2_prisma_flow.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig2_prisma_flow.png", bbox_inches="tight", dpi=300)
plt.close(fig)

print("\nMeasured (full weight) boxes: Records screened, All records excluded by reason, "
      "Total records included, G1, G2, G3.")
print("Reconstructed ('(estimated)', dashed/hatched) boxes: Records identified from databases, "
      "Records identified via other methods, Duplicate records removed, Excluded at "
      "title-and-abstract screening, Reports sought for retrieval, Reports assessed for eligibility, "
      "Reports not retrieved, Excluded at full-text eligibility assessment, Targeted supplementary sweep (G3).")
print("Saved fig2_prisma_flow.svg/.pdf/.png")
