"""
Figure 4 -- treatment schematic (Methods figure, no result magnitudes).
Every illustrative series is real data read from tables/ or the underlying
hourly EDGS output; no series is synthesised.

Headline case: daytime_office, Reference, start=2025, 25-year period
(fit_status=='full'), checked to exist before drawing. This is the
2025/25yr case of Fig. 5 and Table 3; there is no literal 27-year row
(start years in the data are only 2025, 2027, 2030), and 2025+25yr is the
longest non-truncated option.

For legibility, each panel (b)/(c)/(d) is
drawn in the colour of the collapse that produces it (temporal=blue,
spatial=vermillion, trajectory=green), matching the arrows and the
equation below. Each panel also carries a faint "ghost" of the PRIOR
panel's series in the prior panel's own colour, so the collapse is visible
within the panel itself, not just inferred from the arrow above it.
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
TABLES = ROOT / "tables"
FIGS = ROOT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)
HOURLY_EF_PARQUET = Path(r"C:\Users\ehsan\OneDrive - AUT University\PhD\Database\Grid Emission Factor\output\edgs\edgs_hourly_emission_factor_Reference.parquet")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL, BASE  # noqa: E402

set_journal_style()
# Temporal=CATEGORICAL[0] (deep navy), spatial=CATEGORICAL[1] (amber print),
# trajectory=CATEGORICAL[2] (carbon teal); baseline (panel a) = steel blue,
# a neutral tone distinct from all three collapse colours.
BASELINE_C = BASE["steel_blue"]
TEMPORAL_C, SPATIAL_C, TRAJECTORY_C = CATEGORICAL[0], CATEGORICAL[1], CATEGORICAL[2]

# Gate: confirm the headline row exists with fit_status == 'full'
decomp = pd.read_csv(TABLES / "phase3_decomposition_full.csv")
hl = decomp[(decomp["load_shape"] == "daytime_office") & (decomp["scenario"] == "Reference") &
            (decomp["start_year"] == 2025) & (decomp["study_period_yrs_requested"] == 25)]
assert len(hl) == 1, "headline row not found"
hl = hl.iloc[0]
assert hl["fit_status"] == "full", f"headline fit_status is {hl['fit_status']!r}, not 'full'"
START_YEAR = int(hl["start_year"])
PERIOD_YRS = int(hl["study_period_yrs_requested"])
END_YEAR = START_YEAR + PERIOD_YRS - 1
print(f"Headline row confirmed: start={START_YEAR}, period={PERIOD_YRS}yr, "
      f"fit_status={hl['fit_status']}, order_check_total_matches={hl['order_check_total_matches']}")

# Panel data -- all real, all read from tables/ or the hourly EDGS parquet
# (a) one representative week of hourly NI generation-basis EF, start year --
# the first full Mon-Sun week of the start year, so the choice is a fixed,
# reproducible rule rather than a cherry-picked window.
hourly = pd.read_parquet(HOURLY_EF_PARQUET)
hourly["datetime_hour"] = pd.to_datetime(hourly["datetime_hour"])
ni_gen = hourly[(hourly["island"] == "NI") & (hourly["ef_basis"] == "generation")].copy()
jan1 = pd.Timestamp(year=START_YEAR, month=1, day=1)
first_monday = jan1 + pd.Timedelta(days=(7 - jan1.weekday()) % 7)
week_start, week_end = first_monday, first_monday + pd.Timedelta(days=7)
week = ni_gen[(ni_gen["datetime_hour"] >= week_start) & (ni_gen["datetime_hour"] < week_end)].sort_values("datetime_hour")
assert len(week) == 168, f"expected 168 hours, got {len(week)}"
a_hours = np.arange(168)
a_vals = week["emission_factor_kg_co2e_per_kwh"].to_numpy()
a_mean = a_vals.mean()

# (b) annual island mean per year, headline period
isl = pd.read_csv(TABLES / "phase3_annual_island_ef.csv")
b_series = isl[(isl["scenario"] == "Reference") & (isl["island"] == "NI") &
               (isl["year"].between(START_YEAR, END_YEAR))].sort_values("year")
assert len(b_series) == PERIOD_YRS

# (c) annual national mean per year, headline period
nat = pd.read_csv(TABLES / "phase3_annual_national_ef.csv")
c_series = nat[(nat["scenario"] == "Reference") & (nat["year"].between(START_YEAR, END_YEAR))].sort_values("year")
assert len(c_series) == PERIOD_YRS

# (d) static base-year national value -- E_d is defined as base_national_ef * n_years
# (a cumulative quantity, per scripts/phase3_decomposition.py); the per-year rate is
# E_d / n_years, which equals the start-year national annual EF.
d_value = hl["E_d_static_base"] / hl["n_years_used"]
d_value_from_series = c_series[c_series["year"] == START_YEAR]["annual_national_ef"].iloc[0]
assert abs(d_value - d_value_from_series) < 1e-6, "static base value disagrees with annual_national_ef series"

y_max = max(a_vals.max(), b_series["annual_island_ef"].max(), c_series["annual_national_ef"].max(), d_value) * 1.15
y_min = 0

# Draw
fig, axes = plt.subplots(1, 4, figsize=(10.2, 4.8), sharey=True)

def tag(ax, text, color):
    """Small colour-matched corner tag naming the collapse this panel embodies,
    so the story reads locally within the panel, not just from the arrow above."""
    ax.text(0.97, 0.95, text, transform=ax.transAxes, ha="right", va="top",
             fontsize=7.4, fontweight="bold", color=color,
             bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=color, linewidth=1.0, alpha=0.9))

ax = axes[0]
ax.plot(a_hours, a_vals, color=BASELINE_C, lw=1.0)
ax.set_title("(a) Full hourly,\nisland-resolved", fontsize=9.2, loc="center", fontweight="bold")
ax.set_xlabel(f"Hour of representative week\n({week_start.date()} \u2013 {(week_end - pd.Timedelta(hours=1)).date()})", fontsize=6.8)
ax.set_ylabel("Emission factor (kgCO$_2$e/kWh)", fontsize=8.2)
ax.set_xticks([0, 84, 167])
ax.set_xticklabels(["Mon 00:00", "Thu 12:00", "Sun 23:00"], fontsize=6.4)
tag(ax, "baseline", BASELINE_C)

ax = axes[1]
ax.axhline(a_mean, color=BASELINE_C, lw=1.0, ls=(0, (1, 1.4)), alpha=0.55, zorder=1)
ax.step(b_series["year"], b_series["annual_island_ef"], where="mid", color=TEMPORAL_C, lw=2.0, zorder=2)
ax.set_title("(b) Annual island\nmean", fontsize=9.2, loc="center", fontweight="bold", color=TEMPORAL_C)
ax.set_xlabel("Year", fontsize=7.6)
ax.set_xticks([START_YEAR, END_YEAR])
tag(ax, "→ temporal collapse", TEMPORAL_C)

ax = axes[2]
ax.step(b_series["year"], b_series["annual_island_ef"], where="mid", color=TEMPORAL_C, lw=1.4,
         alpha=0.4, ls=(0, (1, 1.4)), zorder=1)
ax.step(c_series["year"], c_series["annual_national_ef"], where="mid", color=SPATIAL_C, lw=2.0, zorder=2)
ax.set_title("(c) Annual national\nmean", fontsize=9.2, loc="center", fontweight="bold", color=SPATIAL_C)
ax.set_xlabel("Year", fontsize=7.6)
ax.set_xticks([START_YEAR, END_YEAR])
tag(ax, "→ spatial collapse", SPATIAL_C)

ax = axes[3]
ax.step(c_series["year"], c_series["annual_national_ef"], where="mid", color=SPATIAL_C, lw=1.4,
         alpha=0.4, ls=(0, (1, 1.4)), zorder=1)
ax.axhline(d_value, color=TRAJECTORY_C, lw=2.2, zorder=2)
ax.set_title(f"(d) Static base-year\nnational ({START_YEAR})", fontsize=9.2, loc="center", fontweight="bold", color=TRAJECTORY_C)
ax.set_xlabel("Year", fontsize=7.6)
ax.set_xticks([START_YEAR, END_YEAR])
ax.set_xlim(START_YEAR, END_YEAR)
tag(ax, "→ trajectory collapse", TRAJECTORY_C)

for ax in axes:
    ax.set_ylim(y_min, y_max)
    ax.tick_params(axis="y", labelsize=7.2)
    ax.grid(axis="y", color="#EEEEEE", lw=0.7, zorder=0)

# Transition arrows above the panels, colour-matched to the equation
fig.canvas.draw()
renderer = fig.canvas.get_renderer()

def panel_center_fig_x(ax):
    bbox = ax.get_window_extent(renderer=renderer)
    return fig.transFigure.inverted().transform([(bbox.x0 + bbox.x1) / 2, 0])[0]

centers = [panel_center_fig_x(ax) for ax in axes]
arrow_y = 0.90
labels = [("when\n(temporal)", TEMPORAL_C), ("where\n(spatial)", SPATIAL_C),
          ("which future\n(trajectory)", TRAJECTORY_C)]
for i, (label, color) in enumerate(labels):
    x1, x2 = centers[i], centers[i + 1]
    fig.add_artist(plt.Line2D([x1 + 0.01, x2 - 0.01], [arrow_y, arrow_y], color=color, lw=2.2,
                               transform=fig.transFigure,
                               solid_capstyle="round", zorder=5))
    fig.add_artist(plt.matplotlib.patches.FancyArrow(
        x2 - 0.035, arrow_y, 0.02, 0, width=0.0006, head_width=0.014, head_length=0.016,
        color=color, transform=fig.transFigure, length_includes_head=True, zorder=5))
    fig.text((x1 + x2) / 2, arrow_y + 0.018, label, ha="center", va="bottom",
              fontsize=8.6, fontweight="bold", color=color)

# Telescoping identity, colour-matched terms.
# matplotlib's mathtext has no \underbrace/\color, so the equation is built
# as a sequence of separately-coloured text runs placed left to right, each
# positioned from the rendered width of the run before it (measured via the
# actual renderer, not an assumed character width).
eq_y = 0.05
lead = r"$E_d - E_a \;=\;$ "
terms = [
    (lead, "#222222"),
    (r"$(E_b - E_a)$", TEMPORAL_C),
    (r"$\;+\;$", "#222222"),
    (r"$(E_c - E_b)$", SPATIAL_C),
    (r"$\;+\;$", "#222222"),
    (r"$(E_d - E_c)$", TRAJECTORY_C),
]
sub_labels = [None, "temporal", None, "spatial", None, "trajectory"]

fig.canvas.draw()
renderer = fig.canvas.get_renderer()
total_w = 0.0
widths = []
for text, color in terms:
    t = fig.text(0, eq_y, text, ha="left", va="bottom", fontsize=11.5, color=color)
    fig.canvas.draw()
    bbox = t.get_window_extent(renderer=renderer)
    w = fig.transFigure.inverted().transform((bbox.width, 0))[0] - fig.transFigure.inverted().transform((0, 0))[0]
    widths.append(w)
    total_w += w
    t.remove()

x = 0.5 - total_w / 2
for (text, color), w, sub in zip(terms, widths, sub_labels):
    fig.text(x, eq_y, text, ha="left", va="bottom", fontsize=11.5, color=color)
    if sub:
        fig.text(x + w / 2, eq_y - 0.052, sub, ha="center", va="top", fontsize=7.8,
                  color=color, fontweight="bold")
    x += w

legend_elems = [
    Line2D([0], [0], color=BASELINE_C, lw=2.0, label="(a) hourly baseline"),
    Line2D([0], [0], color=TEMPORAL_C, lw=2.0, label="(b) temporal collapse (a\u2192b)"),
    Line2D([0], [0], color=SPATIAL_C, lw=2.0, label="(c) spatial collapse (b\u2192c)"),
    Line2D([0], [0], color=TRAJECTORY_C, lw=2.0, label="(d) trajectory collapse (c\u2192d)"),
    Line2D([0], [0], color=BASE["muted_slate"], lw=1.4, ls=(0, (1, 1.4)), alpha=0.6,
           label="faint = prior panel's series, for comparison"),
]
fig.legend(handles=legend_elems, loc="upper left", bbox_to_anchor=(1.0, 0.98),
           frameon=False, fontsize=8.0, borderaxespad=0)

# Marginal note naming the two start years used
# elsewhere in the paper, in the same rounded-box "tag" style as the
# per-panel annotations above, so a reader moving between this Methods
# figure and the Results figures (which show both 2025 and 2027) is
# not confused by an apparent mismatch. This is a Methods illustration
# with no result magnitude of its own -- the note names the two years,
# not a value.
COMPARISON_START_YEAR = 2027  # named alongside START_YEAR (2025 headline), matches Fig. 5's comparison case
fig.text(1.0, 0.60,
          f"Two start years appear across this paper's figures:\n"
          f"{START_YEAR} (headline, this figure and Fig. 5) and\n"
          f"{COMPARISON_START_YEAR} (comparison, Fig. 5) -- both inside the\n"
          f"2024-2050 EDGS horizon; see Methods for why both are shown.",
          transform=fig.transFigure, ha="left", va="top", fontsize=7.0, color=BASE["steel_blue"], style="italic",
          bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor=BASE["steel_blue"], linewidth=0.8, alpha=0.95))

fig.suptitle(f"Fig. 4. The four treatments and three collapses "
             f"(headline case: daytime-office, Reference, {START_YEAR}, {PERIOD_YRS}-year)",
             fontsize=10.4, fontweight="bold", y=1.08)

fig.subplots_adjust(top=0.70, bottom=0.24, wspace=0.5)

fig.savefig(FIGS / "fig4_treatment_schematic.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig4_treatment_schematic.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig4_treatment_schematic.png", bbox_inches="tight", dpi=300)
plt.close(fig)
print("Saved fig4_treatment_schematic.svg/.pdf/.png")
print(f"Panel (a): {len(a_vals)} real hourly values, {week_start.date()}-{(week_end-pd.Timedelta(hours=1)).date()}, "
      f"range [{a_vals.min():.4f}, {a_vals.max():.4f}], mean {a_mean:.4f}")
print(f"Panel (b): {len(b_series)} years, range [{b_series['annual_island_ef'].min():.4f}, "
      f"{b_series['annual_island_ef'].max():.4f}]")
print(f"Panel (c): {len(c_series)} years, range [{c_series['annual_national_ef'].min():.4f}, "
      f"{c_series['annual_national_ef'].max():.4f}]")
print(f"Panel (d): flat value {d_value:.4f} (E_d/{int(hl['n_years_used'])}, matches annual_national_ef "
      f"{START_YEAR}={d_value_from_series:.4f})")
print(f"Shared y-axis: [{y_min}, {y_max:.4f}]")
