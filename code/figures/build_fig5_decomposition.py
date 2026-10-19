"""
Figure 5 -- decomposition (rebuild of fig1_decomposition_spatial_dominance
from phase4_figures.py). Kept: horizontal bars from zero, bar length = mean
of the two decomposition orders, a bracket for the order range, colour by
sign, value labels on every bar, a plain-language title.

Changed (per the Results-section corrections):
  1. Bars are in kgCO2e/m2 at the median intensity, read from
     phase3_decomposition_contextualised_v3_finalEUI.csv (not a hardcoded
     EUI constant -- the per-row EUI scale factor is recovered from the
     table itself: kgco2_m2_a_mid / E_a_hourly_island).
  2. A fourth bar shows the total error, so spatial visibly exceeds it.
  3. The title is composed at run time from the computed values.

Case: daytime_office, Reference. HEADLINE = start=2025, 25-year period
(fit_status 'full'). There is no literal 27-year row in the data (start
years are only 2025, 2027, 2030); 2025+25yr is the longest non-truncated
option covering close to the full modelled horizon.

Flag 1 (three-flags resolution pass): the manuscript text now caveats the
2025 headline start year because it falls inside the 2024-2025 window that
Methods documents as carrying a ~30% validation gap against metered data,
and states three options without picking one. This figure now carries that
same conditionality visually rather than showing only 2025: a second,
visually subordinate bar set for the 2027-start/10-year case (drawn from
the same source table) sits beside each headline bar. The figure only
draws if the two start years agree in sign and ranking -- if they didn't,
that would be a genuine finding requiring a stop, not a styling choice
(checked below, and printed either way).
"""
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"
FIGS = ROOT / "figures"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL, BASE  # noqa: E402

set_journal_style()
# Understate = CATEGORICAL[0] (deep navy). Overstate is a FILLED bar, so per
# the palette rules it uses amber_fill (never the raw print-amber) with a
# dark edgecolor -- amber_print is reserved for lines/markers/text.
UNDERSTATE, OVERSTATE = CATEGORICAL[0], BASE["amber_fill"]
TOTAL_C = BASE["steel_blue"]

decomp = pd.read_csv(TABLES / "phase3_decomposition_contextualised_v3_finalEUI.csv")

CATS = ["Spatial\n(island → national)", "Temporal\n(hourly → annual)",
        "Trajectory\n(evolving → static)", "Total error\n(E$_d$ − E$_a$)"]

def load_case(start_year, period, label):
    row = decomp[(decomp["load_shape"] == "daytime_office") & (decomp["scenario"] == "Reference") &
                 (decomp["start_year"] == start_year) & (decomp["study_period_yrs_requested"] == period)]
    assert len(row) == 1, f"{label}: row not found"
    row = row.iloc[0]
    assert row["fit_status"] == "full", f"{label}: fit_status is {row['fit_status']!r}, not 'full'"
    scale = row["kgco2_m2_a_mid"] / row["E_a_hourly_island"]
    chosen = {
        "Temporal\n(hourly → annual)": row["kgco2_m2_b_mid"] - row["kgco2_m2_a_mid"],
        "Spatial\n(island → national)": row["kgco2_m2_c_mid"] - row["kgco2_m2_b_mid"],
        "Trajectory\n(evolving → static)": row["kgco2_m2_d_mid"] - row["kgco2_m2_c_mid"],
        "Total error\n(E$_d$ − E$_a$)": row["total_error_kgco2_m2_mid"],
    }
    alt = {
        "Temporal\n(hourly → annual)": row["temporal_alt_component"] * scale,
        "Spatial\n(island → national)": row["spatial_alt_component"] * scale,
        "Trajectory\n(evolving → static)": row["kgco2_m2_d_mid"] - row["kgco2_m2_c_mid"],
        "Total error\n(E$_d$ − E$_a$)": row["total_error_kgco2_m2_mid"],
    }
    mid = {c: (chosen[c] + alt[c]) / 2 for c in CATS}
    return dict(row=row, scale=scale, chosen=chosen, alt=alt, mid=mid)

headline = load_case(2025, 25, "headline (2025/25yr)")
compare = load_case(2027, 10, "comparison (2027/10yr)")

# Gate: sign and ranking must agree before drawing. This is exactly the
# check Flag 1 asked for -- a genuine mismatch here would be a finding, not
# a presentation problem, and the script must stop rather than draw over it.
h_total, c_total = headline["mid"]["Total error\n(E$_d$ − E$_a$)"], compare["mid"]["Total error\n(E$_d$ − E$_a$)"]
sign_agrees = (h_total < 0) == (c_total < 0)

component_cats = ["Spatial\n(island → national)", "Temporal\n(hourly → annual)", "Trajectory\n(evolving → static)"]
h_rank = sorted(component_cats, key=lambda c: -abs(headline["mid"][c]))
c_rank = sorted(component_cats, key=lambda c: -abs(compare["mid"][c]))
ranking_agrees = h_rank == c_rank

print("=== Flag 1 gate: 2025 vs 2027 headline comparison ===")
print(f"2025/25yr total error: {h_total:.2f} kgCO2e/m2 ({headline['row']['total_error_pct_of_Ea']:.1f}% of Ea), "
      f"sign={'negative (understates)' if h_total < 0 else 'positive (overstates)'}")
print(f"2027/10yr total error: {c_total:.2f} kgCO2e/m2 ({compare['row']['total_error_pct_of_Ea']:.1f}% of Ea), "
      f"sign={'negative (understates)' if c_total < 0 else 'positive (overstates)'}")
print(f"Sign agrees: {sign_agrees}")
print(f"2025 component ranking (abs, descending): {[c.split(chr(10))[0] for c in h_rank]}")
print(f"2027 component ranking (abs, descending): {[c.split(chr(10))[0] for c in c_rank]}")
print(f"Ranking agrees: {ranking_agrees}")

if not (sign_agrees and ranking_agrees):
    print("\n*** STOP: 2025 and 2027 headline cases disagree in sign and/or ranking. ***")
    print("*** This is a genuine finding, not a presentation issue -- figure NOT drawn. ***")
    sys.exit(1)

print("\nBoth starting points give the same sign and the same component ranking -- proceeding to draw.")

# Draw -- paired bars per category: headline (2025/25yr, full weight) above,
# comparison (2027/10yr, subordinate: reduced alpha + hatch) below.
fig, ax = plt.subplots(figsize=(7.6, 5.2))
n_cat = len(CATS)
y_group = np.arange(n_cat)[::-1] * 1.3  # extra vertical room per category for the paired bars
DY = 0.28  # offset between the headline bar and the comparison bar within a category

def draw_bar(ypos, v_mid, v_chosen, v_alt, is_total, subordinate):
    is_overstate = (not is_total) and v_mid >= 0
    bar_color = TOTAL_C if is_total else (UNDERSTATE if v_mid < 0 else OVERSTATE)
    edge = BASE["deep_navy"] if is_overstate else ("none" if is_total else "white")
    edge_lw = 0.9 if is_overstate else 0.6
    height = 0.42 if not subordinate else 0.34
    alpha = (0.85 if is_total else 1.0) if not subordinate else 0.42
    hatch = "//" if is_total else ("...." if subordinate else None)
    ax.barh(ypos, v_mid, height=height, color=bar_color, zorder=2,
            edgecolor=edge, linewidth=edge_lw, hatch=hatch, alpha=alpha)
    lo, hi = min(v_chosen, v_alt), max(v_chosen, v_alt)
    if abs(hi - lo) > 0.3 and not is_total:
        bc = BASE["steel_blue"] if not subordinate else BASE["muted_slate"]
        ax.plot([lo, hi], [ypos, ypos], color=bc, lw=1.2, zorder=3, solid_capstyle="round",
                 alpha=1.0 if not subordinate else 0.6)
        ax.plot([lo, lo], [ypos - 0.07, ypos + 0.07], color=bc, lw=1.2, zorder=3, alpha=1.0 if not subordinate else 0.6)
        ax.plot([hi, hi], [ypos - 0.07, ypos + 0.07], color=bc, lw=1.2, zorder=3, alpha=1.0 if not subordinate else 0.6)
    label_x = v_mid + (4 if v_mid >= 0 else -4)
    ha = "left" if v_mid >= 0 else "right"
    fontsize = 9.5 if not subordinate else 7.6
    weight = "bold" if not subordinate else "normal"
    color = BASE["deep_navy"] if not subordinate else BASE["steel_blue"]
    ax.text(label_x, ypos, f"{v_mid:+.0f}", va="center", ha=ha, fontsize=fontsize, fontweight=weight, color=color)

for ypos, cat in zip(y_group, CATS):
    is_total = cat.startswith("Total")
    draw_bar(ypos + DY, headline["mid"][cat], headline["chosen"][cat], headline["alt"][cat], is_total, subordinate=False)
    draw_bar(ypos - DY, compare["mid"][cat], compare["chosen"][cat], compare["alt"][cat], is_total, subordinate=True)

ax.axvline(0, color=BASE["muted_slate"], lw=1, zorder=1)
ax.set_yticks(y_group)
ax.set_yticklabels(CATS, fontsize=10)
ax.set_xlabel(f"Contribution (kgCO$_2$e/m$^2$, at median EUI {headline['scale']:.0f} kWh/m$^2$/yr)\n"
              f"Negative = pulls the static/national estimate below the true value; positive = pulls it above")

all_vals = (list(headline["chosen"].values()) + list(headline["alt"].values()) +
            list(compare["chosen"].values()) + list(compare["alt"].values()))
ax.set_xlim(min(all_vals) * 1.25, max(all_vals) * 1.4 + 10)
ax.set_ylim(y_group.min() - 0.85, y_group.max() + 0.85)

# title composed at run time
spatial_mid = headline["mid"]["Spatial\n(island → national)"]
total_mid = headline["mid"]["Total error\n(E$_d$ − E$_a$)"]
exceeds = abs(spatial_mid) > abs(total_mid)
title = "Error components of the static national treatment, North Island daytime office, Reference trajectory"
ax.set_title(title, fontsize=10.5, loc="left", pad=32)

# Caption addendum, composed at run time from both rows' own values
addendum = (f"Headline: {int(headline['row']['start_year'])} start, "
            f"{int(headline['row']['study_period_yrs_requested'])}yr "
            f"({h_total:+.0f} kgCO$_2$e/m$^2$, {headline['row']['total_error_pct_of_Ea']:+.0f}% of E$_a$). "
            f"Comparison (2024–2025 validation-gap check): "
            f"{int(compare['row']['start_year'])} start, {int(compare['row']['study_period_yrs_requested'])}yr "
            f"({c_total:+.0f} kgCO$_2$e/m$^2$, {compare['row']['total_error_pct_of_Ea']:+.0f}% of E$_a$) "
            f"(same sign, same component ranking).")
fig.text(0.01, -0.30, addendum, fontsize=8.2, ha="left", va="top", color=BASE["steel_blue"], style="italic",
          wrap=True, transform=ax.transAxes)

legend_elems = [
    Line2D([0], [0], color=BASE["steel_blue"], lw=1.4, marker="|", markersize=8, label="range across two calculation orders"),
    Line2D([0], [0], marker="s", color="none", markerfacecolor=UNDERSTATE, markersize=10, label="pulls estimate too low"),
    Line2D([0], [0], marker="s", color="none", markerfacecolor=OVERSTATE, markeredgecolor=BASE["deep_navy"], markersize=10, label="pulls estimate too high"),
    Line2D([0], [0], marker="s", color="none", markerfacecolor=TOTAL_C, markersize=10, alpha=0.85, label="total error (order-invariant)"),
    Patch(facecolor=BASE["muted_slate"], edgecolor="none", label="headline: 2025 start, 25yr"),
    Patch(facecolor=BASE["muted_slate"], edgecolor=BASE["steel_blue"], alpha=0.42, hatch="....",
          label="comparison: 2027 start, 10yr"),
]
ax.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(1.02, 1.0),
          frameon=False, fontsize=8.2, borderaxespad=0)

fig.savefig(FIGS / "fig5_decomposition.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig5_decomposition.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig5_decomposition.png", bbox_inches="tight", dpi=300)
plt.close(fig)

print(f"\nHeadline row: daytime_office/Reference/2025/25yr, fit_status={headline['row']['fit_status']}")
print(f"Comparison row: daytime_office/Reference/2027/10yr, fit_status={compare['row']['fit_status']}")
print(f"EUI scale recovered from table: {headline['scale']:.4f} kWh/m2/yr")
print(f"Title: {title}")
print(f"Caption addendum: {addendum}")
print("Saved fig5_decomposition.svg/.pdf/.png")
