"""
Data-driven matplotlib figures that check the numbers and assessments of the
validation report. Every chart is computed from the pipeline's released output
(or, for fig_E, re-derived from the same MBIE workbook the Category D check
uses), not hand-drawn or illustrative. Each figure prints the statistic it checks
on the axes, so the number in the report and the number on the chart come from
the same computation.

Run from anywhere; paths are resolved relative to this file.
"""
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT_DIR = HERE / "figures"
OUT_DIR.mkdir(exist_ok=True)

# Palette: bright/print theme, light ground, flat fills, no gradients or
# shadows. Accent hues (teal/amber/steel) are those of the dark theme; only
# the ground and ink change to a bright register.
NAVY = "#1A2744"          # ink: titles, axis labels, dark text-on-light
STEEL_DARK = "#1E2B3D"    # unused as a background here; kept for reference
STEEL = "#3A4A5C"         # secondary/muted fills (e.g. "excluded" bars)
TEAL = "#0D7377"          # key accent: primary fills/CI bands
TEAL_LT = "#14919B"       # teal variant: lines, primary bars
AMBER = "#E8A838"         # warm accent: single callout/highlight per chart, fills
AMBER_TEXT = "#A9720C"    # darker amber for TEXT on the bright ground (contrast)
SLATE = "#8896A7"         # unused directly as text here; kept for reference
MUTED = "#5B6B80"         # captions/ticks/reference lines on bright ground
CLOUD = "#E8ECF1"         # light bg: axes panel fill
GRID = "#CBD5E0"          # light gridlines
WHITE = "#FFFFFF"         # page background; also text-on-dark-fill (inside bars)
INK = NAVY

plt.rcParams.update(
    {
        "figure.facecolor": WHITE,
        "axes.facecolor": CLOUD,
        "savefig.facecolor": WHITE,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "grid.color": GRID,
        "grid.alpha": 1.0,
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "legend.facecolor": WHITE,
        "legend.edgecolor": MUTED,
        "legend.labelcolor": INK,
    }
)


def style_axes(ax, title=None):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(MUTED)
    ax.grid(axis="y", linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=INK, pad=12)


# Load real data
month_df = pd.read_csv(HERE / "ipcc_uncertainty_by_island_month.csv")
year_df = pd.read_csv(HERE / "ipcc_uncertainty_by_island_year.csv")
fuel_mix = pd.read_csv(ROOT / "output" / "monthly_fuel_mix_NI_SI.csv")

ni_year = year_df[year_df["island"] == "NI"].sort_values("year")
si_year = year_df[year_df["island"] == "SI"].sort_values("year")
ni_month = month_df[month_df["island"] == "NI"].sort_values(["year", "month"])

# Figure A. NI point EF + IPCC-propagated 95% CI, annual, 2015-2025
# Checks the "±1.34-1.51%" annual band.
fig, ax = plt.subplots(figsize=(10, 5.5))
x = ni_year["year"].to_numpy()
y = ni_year["point_ef_kg_per_mwh"].to_numpy()
lo = ni_year["ci95_lower_kg_per_mwh"].to_numpy()
hi = ni_year["ci95_upper_kg_per_mwh"].to_numpy()

ax.fill_between(x, lo, hi, color=TEAL, alpha=0.35, label="95% CI (IPCC Approach 1)", zorder=2)
ax.plot(x, y, color=TEAL_LT, linewidth=2.5, marker="o", markersize=5, zorder=3, label="NI point EF")

# annotate the actual computed band width at min/max years, pulled from the data
widths_pct = ni_year["ci95_pct_of_point"].to_numpy()
i_max = np.argmax(y)
ax.annotate(
    f"{x[i_max]}: {y[i_max]:.1f} kg/MWh  [{lo[i_max]:.1f}–{hi[i_max]:.1f}], ±{widths_pct[i_max]:.2f}%",
    xy=(x[i_max], y[i_max]), xytext=(x[i_max] - 4.7, y[i_max] + 16),
    color=AMBER_TEXT, fontsize=9.5, fontweight="bold", ha="left",
    arrowprops=dict(arrowstyle="->", color=AMBER_TEXT, lw=1.2),
)
ax.text(
    0.015, 0.04,
    f"band width across 2015–2025: {widths_pct.min():.2f}%–{widths_pct.max():.2f}% of point EF"
    f"  (computed live from ipcc_uncertainty_by_island_year.csv, n={len(ni_year)} years)",
    transform=ax.transAxes, color=MUTED, fontsize=9, va="bottom",
)

ax.set_ylim(150, 278)
style_axes(ax, "NI generation-side EF: point estimate vs. IPCC-propagated 95% CI (2015–2025)")
ax.set_ylabel("kg CO$_2$/MWh")
ax.set_xticks(x)
ax.legend(loc="upper right", frameon=True, fontsize=9.5)
fig.tight_layout()
fig.savefig(OUT_DIR / "py_fig_A_ni_ci_band.png", dpi=180)
plt.close(fig)

# Figure B. Generation coverage: quantified (combustion) vs excluded (geothermal+)
# Checks the "52.2%-75.6%" covered / "24-48% left outside" coverage gap.
fig, ax = plt.subplots(figsize=(10, 5.4))
cov = ni_year["quantified_coverage_pct"].to_numpy()
excl = 100 - cov
ax.bar(x, cov, color=TEAL, label="Quantified (coal+gas+diesel+wood)", zorder=3)
ax.bar(x, excl, bottom=cov, color=STEEL, edgecolor=AMBER, hatch="///", linewidth=0.8,
       label="Excluded (geothermal + residual) — no IPCC combustion EF applies", zorder=3)

for xi, c in zip(x, cov):
    ax.text(xi, c - 4, f"{c:.0f}%", ha="center", va="top", fontsize=8.5, color=WHITE, fontweight="bold")

ax.axhline(100, color=MUTED, linewidth=0.6)
style_axes(ax, "NI generation share the IPCC uncertainty band actually covers, by year")
ax.set_ylabel("% of NI generation")
ax.set_ylim(0, 108)
ax.set_xticks(x)
ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.24), ncol=1, frameon=True, fontsize=9)
month_cov = ni_month["quantified_coverage_pct"].to_numpy()
fig.text(
    0.5, 0.075,
    f"annual range: {cov.min():.1f}%–{cov.max():.1f}% quantified "
    f"({100 - cov.max():.1f}%–{100 - cov.min():.1f}% excluded)",
    ha="center", color=MUTED, fontsize=8.7,
)
fig.text(
    0.5, 0.02,
    f"the report's wider 52.2–75.6% figure is this same data at monthly resolution "
    f"({month_cov.min():.1f}%–{month_cov.max():.1f}% here) — annual rollup smooths it",
    ha="center", color=MUTED, fontsize=8.7,
)
fig.tight_layout(rect=(0.03, 0.13, 0.97, 1))
fig.savefig(OUT_DIR / "py_fig_B_coverage_gap.png", dpi=180)
plt.close(fig)

# Figure C. Distribution of monthly CI width (NI), with dominant-fuel coloring
# Checks the "±2.46-5.62% monthly" band and "GAS dominant in 109/132 months",
# both in one figure, both counted from the data.
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 5), gridspec_kw={"width_ratios": [1.3, 1]})

pct = ni_month["ci95_pct_of_point"].dropna().to_numpy()
ax1.hist(pct, bins=24, color=TEAL_LT, edgecolor=NAVY, linewidth=0.4, zorder=3)
ax1.axvline(pct.mean(), color=AMBER_TEXT, linewidth=1.6, linestyle="--", zorder=4)
ax1.text(
    pct.mean() + 0.08, ax1.get_ylim()[1] * 0.92 if ax1.get_ylim()[1] else 1,
    f"mean = {pct.mean():.2f}%", color=AMBER_TEXT, fontsize=9.5, fontweight="bold",
)
style_axes(ax1, "Monthly CI width, NI (n=132 island-months)")
ax1.set_xlabel("95% CI width (% of that month's point EF)")
ax1.set_ylabel("months")
ax1.text(
    0.02, 0.96,
    f"min {pct.min():.2f}%  •  max {pct.max():.2f}%",
    transform=ax1.transAxes, color=MUTED, fontsize=9, va="top",
)

counts = ni_month["dominant_uncertainty_fuel"].value_counts()
colors_map = {"GAS": TEAL_LT, "CLG": AMBER, "DSL": STEEL, "WOOD": MUTED}
bar_colors = [colors_map.get(k, STEEL) for k in counts.index]
bars = ax2.bar(counts.index, counts.values, color=bar_colors, zorder=3)
for b, v in zip(bars, counts.values):
    ax2.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v}", ha="center", color=INK, fontsize=10, fontweight="bold")
style_axes(ax2, "Which fuel dominates the monthly variance")
ax2.set_ylabel("months (of 132)")
ax2.set_ylim(0, counts.values.max() * 1.22)

fig.tight_layout()
fig.savefig(OUT_DIR / "py_fig_C_monthly_ci_and_dominant_fuel.png", dpi=180)
plt.close(fig)

# Figure D. NI monthly fuel-mix composition (stacked share), showing why
# geothermal cannot be dismissed as immaterial. Checks the ~20-38%
# geothermal share behind Figure B.
ni_fuel = fuel_mix[fuel_mix["island"] == "NI"].copy()
ni_fuel["period"] = pd.to_datetime(dict(year=ni_fuel["year"], month=ni_fuel["month"], day=1))
piv = ni_fuel.pivot_table(index="period", columns="fuel_code", values="share_pct", aggfunc="sum").fillna(0.0)
order = [c for c in ["HYD", "GEO", "GAS", "CLG", "WIN", "WOOD", "SOL", "DSL", "ELE"] if c in piv.columns]
piv = piv[order]
colors_stack = {
    "HYD": STEEL, "GEO": AMBER, "GAS": TEAL_LT, "CLG": "#c0392b",
    "WIN": "#AEBAC8", "WOOD": "#6b8f71", "SOL": "#e8c547", "DSL": "#7f5a83", "ELE": MUTED,
}

fig, ax = plt.subplots(figsize=(11.5, 5.5))
ax.stackplot(
    piv.index, [piv[c] for c in order],
    colors=[colors_stack.get(c, STEEL) for c in order],
    labels=order, alpha=1.0, zorder=3,
)
geo_share = piv["GEO"]
style_axes(ax, "NI monthly generation mix by fuel share, 2015–2025 (source: monthly_fuel_mix_NI_SI.csv)")
ax.set_ylabel("% of NI generation")
ax.set_ylim(0, 100)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=len(order), frameon=False, fontsize=8.5)
fig.text(
    0.5, 0.015,
    f"GEO (amber) share over the period: {geo_share.min():.1f}%–{geo_share.max():.1f}% — "
    "this is what Figure B's 'excluded' band is made of, not a rounding residual.",
    ha="center", color=MUTED, fontsize=8.7,
)
fig.tight_layout(rect=(0, 0.10, 1, 1))
fig.savefig(OUT_DIR / "py_fig_D_ni_fuel_mix_composition.png", dpi=180)
plt.close(fig)

# Figure E. External cross-check: this project's quarterly EF vs MBIE's
# published quarterly national EF. Re-derives the Category D1 check
# (generation_pipeline/validate_ef_database_2015_2025.py, id "D1") from the
# same two source files that script uses, independently, so the r and
# mean|diff| shown are recomputed here, not copied from the stored
# DATA_QUALITY_ASSESSMENT_RESULTS.csv text.
mbie_path = ROOT / "generation_pipeline" / "MBIE_Quarterly_Electricity_Emissions_2026Q1.xlsx"
monthly_ef = pd.read_csv(ROOT / "output" / "monthly_emission_factor_NI_SI.csv")

xl = pd.ExcelFile(mbie_path)
dfm = xl.parse("Electricity EFs", header=None)
q_labels = dfm.iloc[8, 1:].tolist()
co2c, ch4c, n2oc = dfm.iloc[10, 1:].tolist(), dfm.iloc[11, 1:].tolist(), dfm.iloc[12, 1:].tolist()
mb = pd.DataFrame({"qlabel": q_labels, "co2": co2c, "ch4": ch4c, "n2o": n2oc}).dropna(subset=["qlabel"])
mb["mbie_co2e"] = mb["co2"] + mb["ch4"] * 28 + mb["n2o"] * 265

nat = monthly_ef.groupby(["year", "month"]).agg(
    gen=("total_gen_MWh", "sum"), co2=("total_CO2_kg", "sum")
).reset_index()
nat["period"] = pd.to_datetime(nat[["year", "month"]].assign(day=1))
nat["quarter"] = nat["period"].dt.to_period("Q")
qmap = {1: "Mar", 2: "Jun", 3: "Sep", 4: "Dec"}
qagg = nat.groupby("quarter").agg(gen=("gen", "sum"), co2=("co2", "sum")).reset_index()
qagg["qlabel"] = qagg["quarter"].apply(lambda p: f"{qmap[p.quarter]} {str(p.year)[2:]}")
qagg["ours"] = qagg["co2"] / qagg["gen"]
comp = qagg.merge(mb, on="qlabel", how="inner").sort_values("quarter")
comp["diff_pct"] = (comp["ours"] - comp["mbie_co2e"]) / comp["mbie_co2e"] * 100
r_live = comp["ours"].corr(comp["mbie_co2e"])
mad_live = comp["diff_pct"].abs().mean()

fig, (axA, axB) = plt.subplots(
    2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]}
)
qx = comp["quarter"].astype(str).to_numpy()
xi = np.arange(len(qx))
axA.plot(xi, comp["ours"] / 1000.0, color=TEAL_LT, linewidth=2, label="This project (bottom-up, all EA/EMI generation)")
axA.plot(xi, comp["mbie_co2e"] / 1000.0, color=AMBER, linewidth=2, linestyle="--", label="MBIE published (top-down inventory)")
style_axes(axA, "Category D re-derived live: quarterly national EF, this project vs. MBIE (2015–2025)")
axA.set_ylabel("t CO$_2$e/MWh")
axA.legend(loc="upper left", frameon=True, fontsize=9.5)
axA.text(
    0.985, 0.05,
    f"Pearson r = {r_live:.4f}   |   mean |diff| = {mad_live:.1f}%   |   n = {len(comp)} quarters\n"
    f"(report's own D1 result: r=0.9787, mean|diff|=9.8%, n=45 — re-derived here from the same 2 source files)",
    transform=axA.transAxes, ha="right", va="bottom", color=MUTED, fontsize=8.7,
)

axB.bar(xi, comp["diff_pct"], color=[TEAL if v >= 0 else "#c0392b" for v in comp["diff_pct"]], zorder=3)
axB.axhline(0, color=MUTED, linewidth=0.8)
style_axes(axB, "% difference each quarter (this project − MBIE, relative to MBIE)")
axB.set_ylabel("% diff")
step = max(1, len(xi) // 22)
axB.set_xticks(xi[::step])
axB.set_xticklabels(qx[::step], rotation=60, ha="right", fontsize=8)

fig.tight_layout()
fig.savefig(OUT_DIR / "py_fig_E_mbie_crossvalidation_live.png", dpi=180)
plt.close(fig)

# Figure F. Hourly-native uncertainty vs. naive rollup.
# Needs the outputs of build_hourly_fuel_mix.py and run_ipcc_uncertainty_hourly.py
# (the three CSVs read below); if they are missing the figure is skipped with a
# message rather than failing.
hourly_ci_path = HERE / "ipcc_uncertainty_by_island_hour.csv"
daily_ci_path = HERE / "ipcc_uncertainty_by_island_day.csv"
annual_from_hourly_path = HERE / "ipcc_uncertainty_by_island_year_from_hourly.csv"

if hourly_ci_path.exists() and daily_ci_path.exists() and annual_from_hourly_path.exists():
    h_df = pd.read_csv(hourly_ci_path)
    d_df = pd.read_csv(daily_ci_path)
    ay_h = pd.read_csv(annual_from_hourly_path)

    ni_h = h_df[(h_df.island == "NI") & (h_df.point_ef_kg_per_mwh > 0)]["ci95_pct_of_point"]
    ni_d = d_df[(d_df.island == "NI") & (d_df.point_ef_kg_per_mwh > 0)]["ci95_pct_of_point"]
    ni_ay_h = ay_h[ay_h.island == "NI"]["ci95_pct_of_point"]
    ni_ay_m = year_df[year_df.island == "NI"]["ci95_pct_of_point"]  # already loaded above

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1.3, 1]})

    ax1.hist(ni_h, bins=40, color=TEAL_LT, edgecolor=NAVY, linewidth=0.3, zorder=3)
    ax1.axvline(ni_h.mean(), color=AMBER_TEXT, linewidth=1.6, linestyle="--", zorder=4)
    ax1.text(ni_h.mean() + 0.1, ax1.get_ylim()[1] * 0.9, f"mean = {ni_h.mean():.2f}%",
              color=AMBER_TEXT, fontsize=9.5, fontweight="bold")
    style_axes(ax1, f"Native hourly CI width, NI (n={len(ni_h):,} hours)")
    ax1.set_xlabel("95% CI width (% of that hour's point EF)")
    ax1.set_ylabel("hours")
    ax1.text(0.02, 0.96, f"min {ni_h.min():.2f}%  •  max {ni_h.max():.2f}%",
              transform=ax1.transAxes, color=MUTED, fontsize=9, va="top")

    labels = [f"Hourly\n(n={len(ni_h):,})", f"Daily\n(n={len(ni_d):,})",
              f"Annual, rolled\nup from hourly\n(n={len(ni_ay_h)})",
              f"Annual, rolled\nup from monthly\n(n={len(ni_ay_m)})"]
    means = [ni_h.mean(), ni_d.mean(), ni_ay_h.mean(), ni_ay_m.mean()]
    bars = ax2.bar(labels, means, color=[TEAL_LT, TEAL, AMBER, STEEL], zorder=3)
    for b, v in zip(bars, means):
        ax2.text(b.get_x() + b.get_width() / 2, v + max(means) * 0.02, f"{v:.2f}%",
                  ha="center", color=INK, fontsize=9.5, fontweight="bold")
    ax2.set_yscale("log")
    style_axes(ax2, "Mean CI width shrinks sharply on naive rollup")
    ax2.set_ylabel("mean 95% CI width (% of point EF, log scale)")
    ax2.tick_params(axis="x", labelsize=8.5)

    ratio = ni_h.mean() / ni_ay_h.mean()
    hours_per_year = len(ni_h) / ni_ay_h.shape[0]
    caption_lines = [
        f"The ~{ratio:.0f}x collapse from hourly ({ni_h.mean():.2f}%) to annual-from-hourly "
        f"({ni_ay_h.mean():.3f}%) is a statistical artifact of assuming",
        f"~{hours_per_year:,.0f} independent hourly errors compound across each year "
        f"(variance shrinks as 1/n) — not a real reduction in uncertainty.",
        f"The annual-from-monthly figure ({ni_ay_m.mean():.2f}%, already in the report) is "
        f"the more defensible headline number for exactly this reason;",
        "the hourly figure is the new, valid native-resolution product this rebuild adds.",
    ]
    for i, line in enumerate(caption_lines):
        fig.text(0.5, 0.13 - i * 0.032, line, ha="center", color=MUTED, fontsize=8.5)
    fig.tight_layout(rect=(0.02, 0.20, 0.98, 1))
    fig.savefig(OUT_DIR / "py_fig_F_hourly_resolution_artifact.png", dpi=180)
    plt.close(fig)
    print(f"Figure F: hourly CI% mean={ni_h.mean():.2f}%, daily mean={ni_d.mean():.2f}%, "
          f"annual-from-hourly mean={ni_ay_h.mean():.3f}%, annual-from-monthly mean={ni_ay_m.mean():.2f}%")
else:
    print("Figure F skipped: run build_hourly_fuel_mix.py then run_ipcc_uncertainty_hourly.py first.")

print("\nWrote figures to", OUT_DIR)
print(f"Figure E live re-derivation: r={r_live:.4f}, mean|diff|={mad_live:.2f}%, n={len(comp)}")
print(f"Figure B coverage range: {cov.min():.1f}%-{cov.max():.1f}%")
print(f"Figure C monthly CI%: min={pct.min():.2f}% max={pct.max():.2f}% mean={pct.mean():.2f}%")
print(f"Figure C dominant fuel counts: {dict(counts)}")
print(f"Figure D GEO share range: {geo_share.min():.1f}%-{geo_share.max():.1f}%")
