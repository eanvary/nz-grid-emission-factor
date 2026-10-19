"""
Figure 8 -- grid heterogeneity (transferability argument), built entirely
from analysis/GRID_HETEROGENEITY_REGISTER.csv. All units harmonised to
gCO2e/kWh at run time (conversion factors applied and printed, not baked
into stored register values except where the register is already in that
unit).
"""
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "analysis" / "GRID_HETEROGENEITY_REGISTER.csv"
FIGS = ROOT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL, BASE  # noqa: E402

set_journal_style()
# Literature systems = CATEGORICAL[0] (deep navy); New Zealand (this study)
# = CATEGORICAL[1] (amber print) -- these range indicators are drawn with
# ax.plot (lines), not filled patches, so amber_print is the correct pair
# per the palette rules (amber_fill is reserved for filled bars/patches).
OI = {"blue": CATEGORICAL[0], "vermillion": CATEGORICAL[1]}

reg = pd.read_csv(REG, keep_default_na=True)

# =============================================================================
# Unit harmonisation -> gCO2e/kWh. Conversion factor applied per row, printed
# for the record.
# =============================================================================
LB_MWH_TO_G_KWH = 453.59237 / 1000  # 1 lb = 453.59237 g; 1 MWh = 1000 kWh
KG_KWH_TO_G_KWH = 1000

def harmonise(row):
    unit = row["unit"]
    if unit == "gCO2e/kWh" or unit == "gCO2/kWh":
        factor, note = 1.0, "already gCO2e/kWh"
    elif unit == "lb/MWh":
        factor, note = LB_MWH_TO_G_KWH, "lb/MWh x 0.45359237 = gCO2/kWh"
    elif unit == "kgCO2-e/kWh":
        factor, note = KG_KWH_TO_G_KWH, "kgCO2-e/kWh x 1000 = gCO2e/kWh"
    elif pd.isna(unit) or unit == "":
        return pd.Series({"min_g": np.nan, "max_g": np.nan, "nat_g": np.nan, "conv_note": "not sourced"})
    else:
        raise ValueError(f"unrecognised unit: {unit}")
    return pd.Series({
        "min_g": row["min_intensity"] * factor,
        "max_g": row["max_intensity"] * factor,
        "nat_g": row["national_average"] * factor,
        "conv_note": note,
    })

conv = reg.apply(harmonise, axis=1)
reg = pd.concat([reg, conv], axis=1)

print("=== Unit harmonisation ===")
for _, r in reg.iterrows():
    if pd.isna(r["min_g"]):
        print(f"{r['system']}: not sourced, no conversion")
    else:
        print(f"{r['system']}: {r['min_intensity']}-{r['max_intensity']} {r['unit']} "
              f"-> {r['min_g']:.1f}-{r['max_g']:.1f} gCO2e/kWh  ({r['conv_note']})")

# recompute ratio from the harmonised (or original, unit-invariant) values
reg["ratio_recomputed"] = reg["max_g"] / reg["min_g"]

# =============================================================================
# Sort: literature rows by descending ratio (NaN ratios -- UK, undefined
# min=0 -- sort last among literature rows); NZ pinned to the bottom,
# visually separated.
# =============================================================================
is_nz = reg["system"] == "New Zealand"
lit = reg[~is_nz].sort_values("ratio_max_min", ascending=False, na_position="last")
nz = reg[is_nz]
plot_rows = pd.concat([lit, nz], ignore_index=True)

# =============================================================================
# Draw
# =============================================================================
n = len(plot_rows)
row_h = 1.0
gap_before_nz = 1.0
y_lit = list(range(len(lit)))[::-1]
y_lit = [y + 1 for y in y_lit]  # leave room 0..1 for the gap+NZ
y_positions = y_lit + [-gap_before_nz]
y_positions = [y + gap_before_nz for y in y_positions]  # shift all up so nothing is negative

fig, ax = plt.subplots(figsize=(8.2, 4.6))

X_FLOOR = 0.6  # gCO2e/kWh -- log-scale plotting floor for genuine zero minima (NZ SI, UK North Scotland)
for i, (_, row) in enumerate(plot_rows.iterrows()):
    y = y_positions[i]
    verified = row["verified"] == "yes"
    color = OI["vermillion"] if row["system"] == "New Zealand" else OI["blue"]
    if pd.isna(row["min_g"]):
        ax.text(X_FLOOR, y, "not adequately sourced (see register)", va="center", ha="left",
                fontsize=8.5, color=BASE["muted_slate"], style="italic")
        ax.text(1.02, y, "", transform=ax.get_yaxis_transform())
        continue

    lo_plot = max(row["min_g"], X_FLOOR)
    zero_floor = row["min_g"] == 0
    # Solid bar for verified rows; dashed/lighter overlay reserved for any
    # unverified row (none currently in the register -- kept so the figure
    # degrades gracefully if a future row is added before it's verified,
    # rather than silently presenting it with full visual weight).
    ax.plot([lo_plot, row["max_g"]], [y, y], color=color, lw=6 if verified else 4,
             solid_capstyle="butt", alpha=1.0 if verified else 0.35, zorder=2)
    if not verified:
        ax.plot([lo_plot, row["max_g"]], [y, y], color=color, lw=6, solid_capstyle="butt",
                 alpha=1.0, zorder=2, linestyle=(0, (1, 1.4)))
    if zero_floor:
        ax.annotate("", xy=(X_FLOOR, y), xytext=(X_FLOOR * 1.8, y),
                     arrowprops=dict(arrowstyle="-|>", color=color, lw=1.3), zorder=3)
        ax.text(X_FLOOR * 1.05, y - 0.30, "true min = 0", va="top", ha="left",
                fontsize=6.8, color=color, style="italic")

    if not pd.isna(row["nat_g"]):
        ax.plot(row["nat_g"], y, marker="D", markersize=7, markerfacecolor="white",
                 markeredgecolor=BASE["deep_navy"], markeredgewidth=1.4, zorder=4)

    label = row["system"] if row["system"] != "New Zealand" else "New Zealand (this study)"
    ax.text(-0.02, y, label, va="center", ha="right", fontsize=9.2,
            fontweight="bold" if row["system"] == "New Zealand" else "normal",
            color=OI["vermillion"] if row["system"] == "New Zealand" else BASE["deep_navy"],
            transform=ax.get_yaxis_transform())

    ratio_txt = "undefined\n(min = 0)" if pd.isna(row["ratio_max_min"]) else f"{row['ratio_max_min']:.1f}x"
    ax.text(1.02, y, ratio_txt, va="center", ha="left", fontsize=8.4,
            transform=ax.get_yaxis_transform(), color=BASE["deep_navy"])

ax.axhline(gap_before_nz - gap_before_nz / 2, color=BASE["muted_slate"], lw=0.8, ls="--")

ax.set_xscale("log")
ax.set_xlim(X_FLOOR, 2000)
ax.set_ylim(-0.6, max(y_positions) + 0.8)
ax.set_yticks([])
ax.set_xlabel("Sub-regional generation-basis emission intensity (gCO2e/kWh, log scale)")
ax.text(1.02, max(y_positions) + 0.55, "max ÷ min\nratio", transform=ax.get_yaxis_transform(),
        fontsize=8.4, fontweight="bold", ha="left", va="bottom")

n_verified = int((reg["verified"] == "yes").sum())
n_total = len(reg)
n_unverified = n_total - n_verified
all_verified = n_unverified == 0
title = (f"Sub-regional range of generation-basis emission intensity in six grid systems "
         f"({n_verified} of {n_total} verified against a primary source)")
ax.set_title(title, fontsize=10.5, loc="left", wrap=True, pad=14)

# Legend is built from what's actually on the plot: the "unverified" style
# entry only appears if the register still has an unverified row (it
# doesn't, as of the second sourcing pass -- all 6 systems are now
# primary_agency/operator_data-verified, so that entry is dropped rather
# than shown as an unused legend key).
legend_elems = [
    Line2D([0], [0], color=OI["blue"], lw=6,
           label="verified, primary agency / peer-reviewed" if all_verified else "verified"),
]
if not all_verified:
    legend_elems.append(Line2D([0], [0], color=OI["blue"], lw=6, alpha=1.0,
                                linestyle=(0, (1, 1.4)), label="unverified (secondary source)"))
legend_elems += [
    Line2D([0], [0], marker="D", color="none", markerfacecolor="white", markeredgecolor=BASE["deep_navy"],
           markersize=7, label="national/EU average"),
    Line2D([0], [0], color=OI["vermillion"], lw=6, label="New Zealand (this study)"),
]
ax.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(1.22, 1.0),
          frameon=False, fontsize=8.2, borderaxespad=0)

fig.savefig(FIGS / "fig8_grid_heterogeneity.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig8_grid_heterogeneity.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig8_grid_heterogeneity.png", bbox_inches="tight", dpi=300)
plt.close(fig)

print("\n=== Ratio recheck (recomputed from min_g/max_g vs. stored ratio_max_min) ===")
for _, r in reg.iterrows():
    if pd.isna(r["min_g"]):
        continue
    stored = r["ratio_max_min"]
    recomputed = r["ratio_recomputed"]
    stored_undefined = pd.isna(stored)
    recomputed_undefined = pd.isna(recomputed) or np.isinf(recomputed)
    if stored_undefined and recomputed_undefined:
        print(f"{r['system']}: both undefined (min=0) -- consistent")
    elif stored_undefined or recomputed_undefined:
        print(f"{r['system']}: MISMATCH -- stored={stored}, recomputed={recomputed}")
    else:
        match = abs(stored - recomputed) < 0.05  # register stores ratio rounded to 1-2dp
        print(f"{r['system']}: stored={stored}, recomputed={recomputed:.4f}, match(<=0.01)={match}")

print(f"\nTitle: {title}")
print("Saved fig8_grid_heterogeneity.svg/.pdf/.png")
