"""
Figure 2 -- treatment schematic (Methods figure, no result magnitudes).
[Manuscript numbering: this is "Figure 2" in the current text (see
"20260822 Where, when, and which future - Z comments.docx", paragraph 79:
"Figure 2. Schematic of the four-treatment, three-stage decomposition of
static/national emission-factor simplification error"). The script/output
filename retains the repo's internal "fig4_..." naming.]
Every illustrative series is real data read from tables/ or the underlying
hourly EDGS output; no series is synthesised.

Headline case: daytime_office, Reference, start=2025, 25-year period
(fit_status=='full') -- confirmed to exist before drawing (Step 0 gate).

v2 of this script (this revision; the original build_fig4_treatment_schematic.py
is untouched), at the user's request, fixing two problems in the original:

Problem 1 -- panel (b) previously carried a faint axhline "ghost" at a_mean,
the mean of ONE representative week from panel (a), drawn flat across the full
25-year x-axis. Comparing a one-week mean against a 25-year annual series has
no analytical meaning and invites reading the vertical gap between the two
lines as "the temporal error", which is wrong. That ghost is removed from
panel (b) entirely. (Panels (c)/(d)'s faint ghosts are UNCHANGED -- those are
genuinely the prior panel's own plotted series, which the legend correctly
describes; only panel (b)'s was the mismatched one.)

Problem 2 -- the temporal error (E_b - E_a) is not a gap between two annual
factor values; it has two parts, confirmed against Table 6 of the manuscript
during Step 0 verification of this revision (numbers below are against the
corrected, solar-fixed data -- see DATA-VINTAGE CORRECTION note above; the
pre-fix numbers this revision originally shipped with are superseded):
  (i)  weighting-basis part = (generation-weighted annual mean) - (plain
       hourly time-mean). Identical across load-shape profiles (it does not
       depend on demand): -0.085031 kgCO2e/kWh cumulative over 2025-2049
       (-11.39 kgCO2e/m2 at median EUI) for all three profiles.
  (ii) demand-alignment part = (plain hourly time-mean) - (profile's
       demand-weighted mean). This is the part that depends on how building
       demand aligns with hourly carbon intensity: +39.07 kgCO2e/m2 for
       daytime_office, +8.55 for evening_weighted, exactly 0.00 for
       continuous_24_7 (flat demand has no alignment to exploit).
  Their sum reproduces Table 6's corrected temporal_component exactly for
  all three profiles (daytime_office +27.68, evening_weighted -2.84,
  continuous_24_7 -11.39 kgCO2e/m2; table values +27.7/-2.8/-11.4, matching
  to rounding), and the implied E_b (1.917430 kgCO2e/kWh cumulative, i.e.
  256.87 kgCO2e/m2 at median EUI) is identical across all three profiles,
  as required by construction (all three demand shapes share one annual
  energy total).
A single January week cannot illustrate this: Step 0 found the original
representative week's mean sits at the 43rd percentile of the full 2025 NI
hourly distribution, materially below the 2025 annual mean, so shading office
hours on that week alone could visually suggest the wrong sign. Panel (a) is
therefore redrawn as a full-2025 hour-of-week mean profile (mean NI
generation-basis EF for each of the 168 (day-of-week, hour) slots, averaged
over all of 2025), with the two-part mechanism drawn directly onto it: the
generation-weighted annual mean (=panel (b)'s first value), the daytime_office
demand-weighted mean, and (since the two differ by more than 2% of the
y-axis range) the plain hourly time-mean, plus shading over the profile's own
occupied hours.

DATA-VINTAGE CORRECTION (2026-09-16, superseding the note this revision
originally shipped with): output/edgs/edgs_hourly_emission_factor.parquet
(all-scenario) was regenerated on 2026-09-03 to fix a real, documented bug
in edgs_pipeline/build_edgs_dispatch.py -- pre-2024 dispatch templates
(the default CENTRAL_TEMPLATE=2021) carry no Solar fuel code, so solar
generation previously fell back to a FLAT 24-hour spread, i.e. non-zero
solar output at night, "a known-wrong physical impossibility" per the
pipeline's own code comment. The fix (Brief T) replaces that fallback with
the real observed 2024 NI hourly solar shape (zero 18:00-06:00, peaked at
midday). Verified directly: the pre-fix file this script originally used
(edgs_hourly_emission_factor_Reference.parquet, 2026-07-18, single-scenario)
has NI solar generation constant at 78.165 MWh in every hour of a sampled
day; the corrected all-scenario file has it at exactly 0 from 18:00-06:00
and ~220 MWh at midday. This is not a minor correction: recomputing the
daytime_office headline temporal component against the corrected data flips
its sign, from -17.1 to +27.7 kgCO2e/m2 (25yr, median EUI) -- office demand
overlaps the solar-suppressed midday window, so it is CLEANER than the
annual average in every year 2025-2049, not dirtier-then-cleaner as the
pre-fix data implied. phase3_decomposition.py, phase3_contextualise_v2_
finalEUI.py and build_table3_headline.py have been rerun against the
corrected EDGS output (2026-09-16); phase3_annual_island_ef.csv,
phase3_annual_national_ef.csv, phase3_decomposition_full.csv and Table 6
now all reflect the fix. This script now sources ALL of panel (a)'s hourly
data from the same corrected, all-scenario file (filtered scenario==
"Reference"), for consistency with panels (b)-(d) and the corrected Table 6.
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
FIGS = ROOT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)
# All-scenario, solar-fixed files (post 2026-09-03; see DATA-VINTAGE CORRECTION
# above). Filtered to scenario=="Reference" below, same as phase3_decomposition.py.
HOURLY_EF_PARQUET = Path(r"C:\Users\ehsan\OneDrive - AUT University\PhD\Database\Grid Emission Factor\output\edgs\edgs_hourly_emission_factor.parquet")
HOURLY_GEN_PARQUET = Path(r"C:\Users\ehsan\OneDrive - AUT University\PhD\Database\Grid Emission Factor\output\edgs\edgs_hourly_generation.parquet")
# phase3_decomposition_full.csv / phase3_annual_island_ef.csv / phase3_annual_national_ef.csv /
# phase3_load_shapes_stylised.csv no longer exist under Figure/tables/ in this repo (removed by a
# prior "remove superseded backups/stale phase3 analysis" cleanup). Read them from the canonical
# location phase3_decomposition.py / phase3_load_profiles.py actually write to, the same way
# HOURLY_EF_PARQUET above already points at the Database repo's output.
DB_TABLES = Path(r"C:\Users\ehsan\OneDrive - AUT University\PhD\Database\Grid Emission Factor\analysis_paper\tables")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL, BASE  # noqa: E402

set_journal_style()
# Temporal=CATEGORICAL[0] (deep navy), spatial=CATEGORICAL[1] (amber print),
# trajectory=CATEGORICAL[2] (carbon teal); baseline (panel a) = steel blue,
# a neutral tone distinct from all three collapse colours.
BASELINE_C = BASE["steel_blue"]
TEMPORAL_C, SPATIAL_C, TRAJECTORY_C = CATEGORICAL[0], CATEGORICAL[1], CATEGORICAL[2]
REFERENCE_LINE_C = BASE["muted_slate"]  # palette's own documented use: "reference lines, non-focal annotation"
SHADE_C = BASE["cloud"]  # palette's own documented use: "shaded zones/bands only"

# =============================================================================
# Gate: confirm the headline row exists with fit_status == 'full'
# =============================================================================
decomp = pd.read_csv(DB_TABLES / "phase3_decomposition_full.csv")
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

# =============================================================================
# (b) annual island mean per year, headline period -- loaded first since (a)
# now plots a reference line at (b)'s own first value.
# =============================================================================
isl = pd.read_csv(DB_TABLES / "phase3_annual_island_ef.csv")
b_series = isl[(isl["scenario"] == "Reference") & (isl["island"] == "NI") &
               (isl["year"].between(START_YEAR, END_YEAR))].sort_values("year")
assert len(b_series) == PERIOD_YRS
b_2025 = b_series[b_series["year"] == START_YEAR]["annual_island_ef"].iloc[0]

# (c) annual national mean per year, headline period
nat = pd.read_csv(DB_TABLES / "phase3_annual_national_ef.csv")
c_series = nat[(nat["scenario"] == "Reference") & (nat["year"].between(START_YEAR, END_YEAR))].sort_values("year")
assert len(c_series) == PERIOD_YRS

# (d) static base-year national value -- E_d is defined as base_national_ef * n_years
# (a cumulative quantity, per scripts/phase3_decomposition.py); the per-year rate is
# E_d / n_years, which equals the start-year national annual EF.
d_value = hl["E_d_static_base"] / hl["n_years_used"]
d_value_from_series = c_series[c_series["year"] == START_YEAR]["annual_national_ef"].iloc[0]
assert abs(d_value - d_value_from_series) < 1e-6, "static base value disagrees with annual_national_ef series"

# =============================================================================
# (a) 2025 hour-of-week mean profile, NI generation-basis EF -- replaces the
# single representative week. Mean of ALL occurrences of each (day-of-week,
# hour-of-day) slot across the full 2025 calendar year (168 slots).
# =============================================================================
hourly = pd.read_parquet(HOURLY_EF_PARQUET)
hourly["datetime_hour"] = pd.to_datetime(hourly["datetime_hour"])
ni_gen = hourly[(hourly["island"] == "NI") & (hourly["ef_basis"] == "generation") &
                (hourly["scenario"] == "Reference")].copy()
ni_2025 = ni_gen[ni_gen["datetime_hour"].dt.year == START_YEAR].copy()
assert len(ni_2025) == 8760, f"expected 8760 hours in {START_YEAR}, got {len(ni_2025)}"
ni_2025["dow"] = ni_2025["datetime_hour"].dt.dayofweek
ni_2025["hour"] = ni_2025["datetime_hour"].dt.hour

hourweek = (ni_2025.groupby(["dow", "hour"])["emission_factor_kg_co2e_per_kwh"]
            .mean().reset_index().sort_values(["dow", "hour"]))
assert len(hourweek) == 168
a_hours = np.arange(168)
a_vals = hourweek["emission_factor_kg_co2e_per_kwh"].to_numpy()

# Plain (unweighted) time-mean of ALL 8760 hours of 2025 (not the 168-slot
# average above, which is a mean-of-means and differs from it at the ~1e-5
# level since not every slot occurs exactly 52 times in a 365-day year).
plain_mean_2025 = ni_2025["emission_factor_kg_co2e_per_kwh"].mean()

# Generation-weighted annual mean, 2025 -- must equal panel (b)'s first value
gen_hourly = pd.read_parquet(HOURLY_GEN_PARQUET)
gen_hourly["datetime_hour"] = pd.to_datetime(gen_hourly["datetime_hour"])
gen_ni_2025 = (gen_hourly[(gen_hourly["island"] == "NI") & (gen_hourly["scenario"] == "Reference") &
                          (gen_hourly["datetime_hour"].dt.year == START_YEAR)]
               .groupby("datetime_hour", observed=True)["generation_mwh"].sum().reset_index())
ni_2025_w = ni_2025.merge(gen_ni_2025, on="datetime_hour", how="left")
genw_mean_2025 = np.average(ni_2025_w["emission_factor_kg_co2e_per_kwh"], weights=ni_2025_w["generation_mwh"].fillna(0))
assert abs(genw_mean_2025 - b_2025) < 1e-6, "recomputed 2025 generation-weighted mean disagrees with phase3_annual_island_ef.csv"

# daytime_office demand-weighted mean, full 2025 NI hourly series (Step 0 item 4c)
shapes = pd.read_csv(DB_TABLES / "phase3_load_shapes_stylised.csv")
office_shape = shapes[shapes["label"] == "daytime_office"][["dow", "hour", "raw_intensity"]]
ni_2025_office = ni_2025.merge(office_shape, on=["dow", "hour"], how="left")
office_weighted_mean_2025 = np.average(ni_2025_office["emission_factor_kg_co2e_per_kwh"], weights=ni_2025_office["raw_intensity"])

# --- occupied hours of the daytime_office profile ---
# Rule: weekday weight strictly exceeds the shape's own night/evening off-peak
# tier (0.3). NOTE: the office day-block peak weight is 1.0, exactly equal to
# (never exceeding) the continuous_24_7 flat weight of 1.0, so "exceeds the
# flat 24/7 weight" selects zero hours and is not usable here; this shape's
# actual off-peak tiers are 0.2 (night, h0-6) and 0.3 (evening, h18-23), and
# thresholding at 0.3 isolates exactly the day block (h7-17 each weekday).
OCCUPIED_THRESHOLD = 0.3
office_map = shapes[shapes["label"] == "daytime_office"].set_index(["dow", "hour"])["raw_intensity"]
occupied_by_dowhour = office_map > OCCUPIED_THRESHOLD

# =============================================================================
# y-axis range (computed from panel (a)'s NEW data)
# =============================================================================
y_max = max(a_vals.max(), b_series["annual_island_ef"].max(), c_series["annual_national_ef"].max(), d_value) * 1.15
y_min = 0
y_range = y_max - y_min

# Rule (per this revision's brief): draw the plain time-mean line in (a) only
# if it sits at least 2% of the y-axis range away from the annual mean.
plain_gap = abs(genw_mean_2025 - plain_mean_2025)
draw_plain_mean = (plain_gap / y_range) >= 0.02
print(f"Plain-vs-annual-mean gap = {plain_gap:.6f} ({100*plain_gap/y_range:.2f}% of y-range) "
      f"-> {'drawing' if draw_plain_mean else 'omitting'} the plain time-mean line")

# =============================================================================
# Draw
# =============================================================================
fig, axes = plt.subplots(1, 4, figsize=(8.6, 5.6), sharey=True,
                          gridspec_kw={"width_ratios": [1.7, 1, 1, 1]})

def tag(ax, text, color, xy=(0.97, 0.95), va="top"):
    """Small colour-matched corner tag naming the collapse this panel embodies,
    so the story reads locally within the panel, not just from the arrow above."""
    ax.text(xy[0], xy[1], text, transform=ax.transAxes, ha="right", va=va,
             fontsize=7.4, fontweight="bold", color=color,
             bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=color, linewidth=1.0, alpha=0.9))

ax = axes[0]
# Shade occupied daytime_office hours (weekday only; weekend weight never
# exceeds the threshold), behind the data line.
for dow in range(5):  # Mon-Fri only
    day_offset = dow * 24
    occ_hours = [h for h in range(24) if occupied_by_dowhour.get((dow, h), False)]
    if occ_hours:
        ax.axvspan(day_offset + min(occ_hours) - 0.5, day_offset + max(occ_hours) + 0.5,
                   color=SHADE_C, alpha=0.7, zorder=0, lw=0)
ax.text(2.5 * 24, y_max * 0.10, "office occupied hours", ha="center", va="bottom",
         fontsize=6.0, color=BASE["steel_blue"], style="italic")

ax.plot(a_hours, a_vals, color=BASELINE_C, lw=1.0, zorder=3)

# Reference lines: annual mean used in (b), and the office demand-weighted mean.
# The three candidate reference lines (plain/office/annual) sit within ~7% of
# each other on the y-axis, so labelling each one directly on the line (as
# for the shading below) crowds and overlaps the data. Instead they get their
# own small legend below panel (a) (matching handle colour/style to the
# plotted axhlines), well clear of the data.
ax.axhline(genw_mean_2025, color=TEMPORAL_C, lw=1.2, ls=(0, (4, 1.5)), zorder=2, label="annual mean (b)")
ax.axhline(office_weighted_mean_2025, color=REFERENCE_LINE_C, lw=1.2, ls=(0, (4, 1.5)), zorder=2, label="office demand mean")
if draw_plain_mean:
    ax.axhline(plain_mean_2025, color=BASELINE_C, lw=1.0, ls=(0, (1, 1.4)), alpha=0.6, zorder=2, label="plain hourly mean")

ax.set_title("(a) Hourly, island-resolved:\n2025 hour-of-week mean", fontsize=9.2, loc="center", fontweight="bold")
ax.set_xlabel(f"Hour of week (2025 mean per slot)", fontsize=6.8)
ax.set_ylabel("Emission factor (kgCO$_2$e/kWh)", fontsize=8.2)
ax.set_xticks([0, 84, 167])
ax.set_xticklabels(["Mon 00:00", "Thu 12:00", "Sun 23:00"], fontsize=6.4)
ax.set_xlim(0, 167)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.30), frameon=False, fontsize=6.4,
          ncol=1, handlelength=1.8, labelspacing=0.35, borderaxespad=0)
tag(ax, "baseline", BASELINE_C, xy=(0.97, 0.05), va="bottom")

ax = axes[1]
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

# --- transition arrows above the panels, colour-matched to the equation ---
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

# --- telescoping identity, colour-matched terms.
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
           label="faint in (c) and (d) = prior panel's series"),
]
fig.legend(handles=legend_elems, loc="upper center", bbox_to_anchor=(0.5, -0.14),
           frameon=False, fontsize=7.4, ncol=5, columnspacing=1.2, handlelength=1.8, borderaxespad=0)

fig.suptitle(f"Four emission-factor treatments and three collapses, North Island daytime office, "
             f"Reference trajectory, {START_YEAR} start, {PERIOD_YRS}-year period",
             fontsize=10.4, fontweight="bold", y=1.08)

fig.subplots_adjust(top=0.66, bottom=0.34, wspace=0.5)

fig.savefig(FIGS / "fig4_treatment_schematic_v2.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig4_treatment_schematic_v2.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig4_treatment_schematic_v2.png", bbox_inches="tight", dpi=300)
plt.close(fig)
print("Saved fig4_treatment_schematic_v2.svg/.pdf/.png")
print(f"Panel (a): {len(a_vals)} hour-of-week means, {START_YEAR} NI generation-basis, "
      f"range [{a_vals.min():.4f}, {a_vals.max():.4f}]")
print(f"  plain time-mean (2025, all 8760 hours) = {plain_mean_2025:.6f}")
print(f"  generation-weighted annual mean (2025) = {genw_mean_2025:.6f} (matches panel (b) first value: "
      f"{abs(genw_mean_2025 - b_2025) < 1e-6})")
print(f"  daytime_office demand-weighted mean (2025) = {office_weighted_mean_2025:.6f}")
print(f"  weighting-basis gap (annual - plain) = {genw_mean_2025 - plain_mean_2025:.6f}")
print(f"  demand-alignment gap (plain - office-weighted) = {plain_mean_2025 - office_weighted_mean_2025:.6f}")
print(f"Panel (b): {len(b_series)} years, range [{b_series['annual_island_ef'].min():.4f}, "
      f"{b_series['annual_island_ef'].max():.4f}]")
print(f"Panel (c): {len(c_series)} years, range [{c_series['annual_national_ef'].min():.4f}, "
      f"{c_series['annual_national_ef'].max():.4f}]")
print(f"Panel (d): flat value {d_value:.4f} (E_d/{int(hl['n_years_used'])}, matches annual_national_ef "
      f"{START_YEAR}={d_value_from_series:.4f})")
print(f"Shared y-axis: [{y_min}, {y_max:.4f}]")
