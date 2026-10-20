"""
Figure 7: conditional sign. Daytime_office, 25-year nominal period,
grouped by trajectory (scenario) then by start year, coloured by sign,
hatched where truncated.

Further elements:
  - Rows flagged pct_breakdown_unstable are excluded from the bars, not
    only hatched; the exclusion count is stated in the printed caption text.
  - A count strip beneath each trajectory group gives the number of
    negative-error combinations out of the total tested for that
    trajectory. The count spans the full 120-row factorial (all load
    shapes, all periods), not only the 15 bars shown, because that is
    "the total tested" the k-of-n rule refers to.
"""
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"
FIGS = ROOT / "figures"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL, BASE  # noqa: E402

set_journal_style()
# Understate = CATEGORICAL[0] (deep navy). Overstate is a filled bar, so the
# palette rules give it amber_fill (not the raw print-amber) with a dark edge.
UNDERSTATE_C, OVERSTATE_C = CATEGORICAL[0], BASE["amber_fill"]

decomp_full = pd.read_csv(TABLES / "phase3_decomposition_full.csv")
t1 = pd.read_csv(TABLES / "phase4_table1_full_decomposition.csv")
decomp_full = decomp_full.merge(
    t1[["load_shape", "scenario", "start_year", "study_period_yrs_requested", "pct_breakdown_unstable"]],
    on=["load_shape", "scenario", "start_year", "study_period_yrs_requested"], how="left")

# Count strip: negative-error combinations per trajectory, out of the full
# 120-row factorial (all load shapes, all periods)
neg_counts = decomp_full.groupby("scenario").apply(
    lambda g: pd.Series({"n_negative": int((g["total_error_d_minus_a"] < 0).sum()), "n_total": len(g)}),
    include_groups=False)
print("=== Per-trajectory negative-error count strip (full 120-row factorial) ===")
print(neg_counts.to_string())

# Panel data: daytime_office, 25yr nominal, minus rows flagged unstable
s25 = decomp_full[(decomp_full["load_shape"] == "daytime_office") &
                   (decomp_full["study_period_yrs_requested"] == 25)].copy()
n_total_subset = len(s25)
n_excluded = int(s25["pct_breakdown_unstable"].sum())
s25_plot = s25[~s25["pct_breakdown_unstable"]].copy()
print(f"\nPanel subset (daytime_office, 25yr nominal): {n_total_subset} combinations, "
      f"{n_excluded} excluded (pct_breakdown_unstable), {len(s25_plot)} plotted.")

scenario_order = ["Constraint", "Reference", "Growth", "Innovation", "Environmental"]
assert set(scenario_order) == set(decomp_full["scenario"].unique()), "scenario_order out of sync with the data"
start_years = sorted(s25["start_year"].unique())

fig, ax = plt.subplots(figsize=(7.4, 4.6))
width = 0.22
x = np.arange(len(scenario_order))
# one alpha shade per start year, lightest = earliest; a display-order
# choice (3 levels), not a data value
start_year_alphas = np.linspace(0.45, 1.0, len(start_years))

for j, sy in enumerate(start_years):
    offs = (j - 1) * width
    for i, scen in enumerate(scenario_order):
        row = s25_plot[(s25_plot["scenario"] == scen) & (s25_plot["start_year"] == sy)]
        if len(row) == 0:
            continue  # excluded (unstable) or missing
        v = row["total_error_pct_of_Ea"].values[0]
        truncated = row["fit_status"].values[0] != "full"
        overstate = v >= 0
        color = OVERSTATE_C if overstate else UNDERSTATE_C
        edge = BASE["deep_navy"] if overstate else "none"
        b = ax.bar(x[i] + offs, v, width * 0.92, color=color, alpha=start_year_alphas[j],
                   edgecolor=edge, linewidth=0.8 if overstate else 0)
        if truncated:
            b[0].set_hatch("//")

ax.axhline(0, color=BASE["steel_blue"], lw=1.1, zorder=0)
ax.set_xticks(x)
ax.set_xticklabels(scenario_order, fontsize=9.5)
ax.set_ylabel("Total error, $E_d - E_a$ (% of full-resolution $E_a$)")

# Count strip beneath each trajectory group
y_strip = ax.get_ylim()[0] - 0.16 * (ax.get_ylim()[1] - ax.get_ylim()[0])
for i, scen in enumerate(scenario_order):
    n_neg = int(neg_counts.loc[scen, "n_negative"])
    n_tot = int(neg_counts.loc[scen, "n_total"])
    ax.text(x[i], y_strip, f"{n_neg}/{n_tot}\nnegative", ha="center", va="top", fontsize=7.6, color=BASE["deep_navy"])
ax.set_ylim(ax.get_ylim()[0] - 0.28 * (ax.get_ylim()[1] - ax.get_ylim()[0]), ax.get_ylim()[1])

title = (f"Total error of the static national treatment by trajectory and start year, "
         f"North Island daytime office, 25-year period" + (chr(10) if n_excluded else "") +
         (f"({n_excluded} of {n_total_subset} combinations excluded as non-interpretable)" if n_excluded else ""))
ax.set_title(title, fontsize=10.6, loc="left")

legend_elems = [Patch(facecolor=BASE["muted_slate"], alpha=a, label=f"start {sy}")
                for sy, a in zip(start_years, start_year_alphas)]
legend_elems += [
    Patch(facecolor="white", edgecolor=BASE["steel_blue"], hatch="//",
          label=f"truncated period (<{int(s25['study_period_yrs_requested'].iloc[0])}yr available)"),
    Patch(facecolor=UNDERSTATE_C, label="static EF understates"),
    Patch(facecolor=OVERSTATE_C, edgecolor=BASE["deep_navy"], label="static EF overstates")]
ax.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(1.02, 1.0),
          frameon=False, fontsize=8, ncol=1, borderaxespad=0)

fig.savefig(FIGS / "fig7_conditional_sign.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig7_conditional_sign.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig7_conditional_sign.png", bbox_inches="tight", dpi=300)
plt.close(fig)
print("Saved fig7_conditional_sign.svg/.pdf/.png")
print(f"Caption exclusion count: {n_excluded} of {n_total_subset}")
