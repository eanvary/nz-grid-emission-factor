"""
Figure 6: temporal mechanism with the null result. Two claims are kept
visually separate: (1) main panel, the seasonal/diurnal variance-share
shift 2024-2050 (NI, Reference); (2) inset, the null result that diurnal
shape barely moves across the whole horizon, for all five trajectories.

The seasonal-collapse claim must not mix the 2024 month share with the
2050 season share (mixing them gives the misleading "73% to 14%").
Both panel series use eta2_season and eta2_hour consistently at both
endpoints; eta2_month is not plotted. All four endpoint values are
printed for the record.
"""
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"
FIGS = ROOT / "figures"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journal_palette import set_journal_style, CATEGORICAL, LINE_STYLES, BASE  # noqa: E402

set_journal_style()
# Main panel: seasonal = CATEGORICAL[1] (amber print), diurnal = CATEGORICAL[0]
# (deep navy). Inset: 5 scenarios use the full CATEGORICAL sequence. Each is
# paired with its matching LINE_STYLES entry (linestyle+marker) so that the
# 5 series stay distinguishable in greyscale print, per the rule for more
# than two series.
SEASONAL_C, DIURNAL_C = CATEGORICAL[1], CATEGORICAL[0]
SCENARIO_ORDER = ["Constraint", "Environmental", "Growth", "Innovation", "Reference"]
SCEN_COLORS = {s: CATEGORICAL[i] for i, s in enumerate(SCENARIO_ORDER)}
SCEN_STYLES = {s: LINE_STYLES[i] for i, s in enumerate(SCENARIO_ORDER)}

# Endpoint values from the table, all four printed
vd = pd.read_csv(TABLES / "phase1_variance_decomp_by_island.csv")
vd_ni_ref = vd[(vd["scenario"] == "Reference") & (vd["island"] == "NI")].sort_values("year")
endpoints = vd_ni_ref[vd_ni_ref["year"].isin([2024, 2050])]
print("=== Step 1 item 1: NI Reference eta-squared endpoints ===")
print(endpoints[["year", "eta2_hour", "eta2_month", "eta2_season"]].to_string(index=False))
month_2024 = endpoints[endpoints.year == 2024]["eta2_month"].iloc[0]
month_2050 = endpoints[endpoints.year == 2050]["eta2_month"].iloc[0]
season_2024 = endpoints[endpoints.year == 2024]["eta2_season"].iloc[0]
season_2050 = endpoints[endpoints.year == 2050]["eta2_season"].iloc[0]
print(f"eta2_month:  {month_2024*100:.1f}% (2024) to {month_2050*100:.1f}% (2050)")
print(f"eta2_season: {season_2024*100:.1f}% (2024) to {season_2050*100:.1f}% (2050)")
print("The '73% to 14%' claim mixes eta2_month(2024) with eta2_season(2050); it is not reproduced here.")
print("This figure plots eta2_season and eta2_hour consistently at both endpoints.\n")

# Main panel data
main_years = vd_ni_ref["year"]
main_season = vd_ni_ref["eta2_season"] * 100
main_hour = vd_ni_ref["eta2_hour"] * 100

# Inset panel data: diurnal persistence, all 5 trajectories, NI only.
# SI is excluded: its corr_vs_2024 is undefined (NaN) throughout, because
# SI's near-zero generation-side EF makes the correlation degenerate.
# The check below confirms this from the table.
dsp = pd.read_csv(TABLES / "phase1_diurnal_shape_persistence.csv")
dsp_ni = dsp[dsp["island"] == "NI"].copy()
si_all_nan = dsp[dsp["island"] == "SI"]["corr_vs_2024"].isna().all()
print(f"SI corr_vs_2024 all-NaN (confirms NI-only restriction): {si_all_nan}")
min_corr = dsp_ni["corr_vs_2024"].min()
print(f"Minimum diurnal correlation across all NI scenario-years: {min_corr:.4f}")

# Peak-hour check, NI only. SI's peak hour is a structurally distinct
# value (0 against 9 for NI) because SI's EF profile is near-flat and
# noise-dominated. A "peak hour" annotation for SI would therefore not be
# meaningful. The main panel above is also NI-scoped.
dp = pd.read_csv(TABLES / "phase1_diurnal_profiles.csv")
dp_ni = dp[dp["island"] == "NI"]
peak = dp_ni.loc[dp_ni.groupby(["scenario", "year"])["emission_factor_kg_co2e_per_kwh"].idxmax()]
distinct_peaks = sorted(peak["hour"].unique())
peak_identical = len(distinct_peaks) == 1
print(f"Distinct NI peak hours across all scenario-years: {distinct_peaks} "
      f"(identical: {peak_identical})")

# Draw
fig, ax = plt.subplots(figsize=(6.6, 4.2))
ax.plot(main_years, main_season, color=SEASONAL_C, lw=2.2, linestyle=LINE_STYLES[1]["linestyle"])
ax.plot(main_years, main_hour, color=DIURNAL_C, lw=2.2, linestyle=LINE_STYLES[0]["linestyle"])
ax.annotate("Seasonal", xy=(main_years.iloc[-1], main_season.iloc[-1]),
            xytext=(4, 4), textcoords="offset points", color=SEASONAL_C, fontsize=9.5, fontweight="bold")
ax.annotate("Diurnal", xy=(main_years.iloc[-1], main_hour.iloc[-1]),
            xytext=(4, -10), textcoords="offset points", color=DIURNAL_C, fontsize=9.5, fontweight="bold")
ax.set_xlabel("Year")
ax.set_ylabel("Marginal share of hourly EF variance (%)", fontsize=9)
ax.set_xlim(2023, 2054)
ax.yaxis.set_major_formatter(mticker.PercentFormatter())
ax.set_title("Marginal variance shares of the hourly emission factor, North Island, Reference trajectory, 2024–2050", fontsize=10.5, loc="left")

# Inset: the null result. It sits in the upper-right corner of the main
# panel, which the data leave blank: seasonal has dropped below 25% by
# about 2032 and diurnal never rises above about 8%. The inset therefore
# cannot obscure either main-panel series or its direct labels.
ax_ins = fig.add_axes([0.56, 0.46, 0.36, 0.26])
for scen in SCENARIO_ORDER:
    sub = dsp_ni[dsp_ni["scenario"] == scen].sort_values("year")
    style = SCEN_STYLES[scen]
    ax_ins.plot(sub["year"], sub["corr_vs_2024"], color=SCEN_COLORS[scen], lw=1.1,
                linestyle=style["linestyle"], marker=style["marker"], ms=3.2)
floor = np.floor(min_corr * 100) / 100 - 0.01
ax_ins.set_ylim(floor, 1.005)
ax_ins.set_xlim(2023, 2051)
ax_ins.set_xticks([2024, 2050])
ax_ins.tick_params(labelsize=6.6)
ax_ins.set_title("Diurnal shape vs. 2024\n(all 5 trajectories, NI)", fontsize=7.2)
if peak_identical:
    ax_ins.text(0.03, 0.05, f"Peak EF hour: {distinct_peaks[0]:02d}:00\n(every scenario, every year)",
                transform=ax_ins.transAxes, fontsize=6.4, va="bottom", ha="left", style="italic", color=BASE["deep_navy"])
else:
    ax_ins.text(0.03, 0.05, f"Peak EF hour range: {min(distinct_peaks):02d}:00–{max(distinct_peaks):02d}:00\n"
                            f"(not identical across scenarios/years)",
                transform=ax_ins.transAxes, fontsize=6.4, va="bottom", ha="left", style="italic", color=BASE["deep_navy"])
for spine in ax_ins.spines.values():
    spine.set_linewidth(0.6)

# 5-series inset: the styling rules say colour alone is not enough for more
# than two series, and the marker/linestyle redundancy is applied above. A
# compact legend outside the axes states the mapping, following the
# convention for more than three entries used across this figure set. The
# reader then does not have to infer it from the marker legend.
from matplotlib.lines import Line2D
scen_legend = [Line2D([0], [0], color=SCEN_COLORS[s], lw=1.1, linestyle=SCEN_STYLES[s]["linestyle"],
                       marker=SCEN_STYLES[s]["marker"], ms=4, label=s) for s in SCENARIO_ORDER]
ax.legend(handles=scen_legend, loc="upper left", bbox_to_anchor=(1.02, 1.0),
          frameon=False, fontsize=7.2, title="Trajectory (inset)", title_fontsize=7.4, borderaxespad=0)

fig.savefig(FIGS / "fig6_temporal_mechanism.svg", bbox_inches="tight")
fig.savefig(FIGS / "fig6_temporal_mechanism.pdf", bbox_inches="tight")
fig.savefig(FIGS / "fig6_temporal_mechanism.png", bbox_inches="tight", dpi=300)
plt.close(fig)
print("Saved fig6_temporal_mechanism.svg/.pdf/.png")
