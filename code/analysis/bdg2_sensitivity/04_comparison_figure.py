"""
BDG2 real-data sensitivity test (script 4 of 4): comparison figure for the
headline case (Reference, NI, start=2027, 10yr). It sets the spatial and
temporal error shares for the stylised shapes (main assessment, read-only)
beside those for the real BDG2 shapes (this sensitivity branch).
"""
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

MAIN_TABLES = Path(__file__).resolve().parents[3] / "analysis_paper" / "tables"
SELF = Path(__file__).resolve().parents[1]
TABLES = SELF / "tables"
FIGS = SELF / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

OI = {"blue": "#0072B2", "orange": "#E69F00", "vermillion": "#D55E00", "grey": "#999999"}
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none"})

# stylised (main assessment, read-only)
styl = pd.read_csv(MAIN_TABLES / "phase3_decomposition_full.csv")
styl_hl = styl[(styl["scenario"] == "Reference") & (styl["start_year"] == 2027) &
               (styl["study_period_yrs_requested"] == 10)][["load_shape", "spatial_pct_of_total", "temporal_pct_of_total"]]
styl_hl["source"] = "stylised (main assessment)"

# real (this branch)
real = pd.read_csv(TABLES / "real_shape_decomposition_full.csv")
real_hl = real[(real["scenario"] == "Reference") & (real["start_year"] == 2027) &
               (real["study_period_yrs_requested"] == 10)][["load_shape", "spatial_pct_of_total", "temporal_pct_of_total"]]
real_hl["source"] = "real BDG2 (this sensitivity test)"

combined = pd.concat([styl_hl, real_hl], ignore_index=True)
combined = combined.sort_values("spatial_pct_of_total")

fig, ax = plt.subplots(figsize=(7.5, 5.0))
y = range(len(combined))
colors = [OI["blue"] if s == "stylised (main assessment)" else OI["vermillion"] for s in combined["source"]]
markers = ["o" if s == "stylised (main assessment)" else "D" for s in combined["source"]]

for i, (_, row) in enumerate(combined.iterrows()):
    ax.plot([0, row["spatial_pct_of_total"]], [i, i], color="#888888", lw=1, zorder=1, alpha=0.5)
    ax.scatter(row["spatial_pct_of_total"], i, color=OI["blue"] if row["source"].startswith("stylised") else OI["vermillion"],
               marker="o" if row["source"].startswith("stylised") else "D", s=90, zorder=3, edgecolor="white", linewidth=0.7)
    ax.scatter(row["temporal_pct_of_total"], i, color=OI["orange"], marker="|", s=250, zorder=3, linewidth=2.5)

ax.axvline(0, color="#666666", lw=1)
ax.set_yticks(list(y))
ax.set_yticklabels(combined["load_shape"], fontsize=9)
ax.set_xlabel("Share of total decomposition error (%), 10-year period, Reference scenario, start=2027")
ax.set_title("Spatial error exceeds temporal error for EVERY tested load shape\n"
              "3 stylised shapes (main assessment) + 6 real office buildings + their average",
              fontsize=11.5, loc="left")

from matplotlib.lines import Line2D
legend_elems = [
    Line2D([0], [0], marker="o", color="none", markerfacecolor=OI["blue"], markersize=9, label="Spatial share, stylised shape"),
    Line2D([0], [0], marker="D", color="none", markerfacecolor=OI["vermillion"], markersize=8, label="Spatial share, real BDG2 shape"),
    Line2D([0], [0], marker="|", color=OI["orange"], markersize=14, markeredgewidth=2.5, label="Temporal share (either source)"),
]
ax.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False, fontsize=8.5, borderaxespad=0)
fig.savefig(FIGS / "comparison_real_vs_stylised_shapes.svg", bbox_inches="tight")
fig.savefig(FIGS / "comparison_real_vs_stylised_shapes.pdf", bbox_inches="tight")
fig.savefig(FIGS / "comparison_real_vs_stylised_shapes.png", bbox_inches="tight", dpi=150)
plt.close(fig)
print("Saved comparison_real_vs_stylised_shapes.{svg,pdf,png}")
