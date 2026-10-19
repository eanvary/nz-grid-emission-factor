"""
Reconstruction of four supplementary EF figures that existed in output/ with
no corresponding source script anywhere in the repo (annual_EF_bar_NI_SI.png,
daily_EF_variation_NI_SI.png, hourly_EF_diurnal_profile_NI_SI.png,
fuel_mix_share_2025_NI_SI.png). Rebuilt here, matching their original visual
design (confirmed against the pre-existing PNGs backed up in
output/_backup_2021_2025_only/), against the current 2015-2025 pipeline
outputs. Does not touch the EF/generation/HVDC pipeline scripts or outputs.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent  # repo root (this script now lives in generation_pipeline/, one level deeper -- 2026-08 reorg)
OUT_DIR = ROOT / "output"

NAVY = "#1A2744"
TEAL = "#0D7377"
FUEL_COLOURS = {
    "HYD": "#1A6FB5", "GEO": "#A65D2E", "WIN": "#5FB87A",
    "GAS": "#E0A030", "CLG": "#3A3A3A", "DSL": "#B5302E",
    "SOL": "#E8D04A", "WOOD": "#7A5230", "ELE": "#999999",
}

annual = pd.read_csv(OUT_DIR / "annual_emission_factor_NI_SI.csv")
daily = pd.read_csv(OUT_DIR / "daily_emission_factor_NI_SI.csv", parse_dates=["date"])
hourly = pd.read_csv(OUT_DIR / "hourly_emission_factor_NI_SI.csv", parse_dates=["datetime"])
fuel_monthly = pd.read_csv(OUT_DIR / "monthly_fuel_mix_NI_SI.csv")

yr_min, yr_max = int(annual["year"].min()), int(annual["year"].max())

# 1: Annual generation-weighted EF bar chart, NI vs SI
years = sorted(annual["year"].unique())
ni_ef = annual[annual.island == "NI"].set_index("year")["EF_kg_per_MWh"].reindex(years)
si_ef = annual[annual.island == "SI"].set_index("year")["EF_kg_per_MWh"].reindex(years)

fig, ax = plt.subplots(figsize=(max(10, len(years) * 0.9), 6))
x = np.arange(len(years))
w = 0.38
b1 = ax.bar(x - w / 2, ni_ef, width=w, color=NAVY, label="North Island")
b2 = ax.bar(x + w / 2, si_ef, width=w, color=TEAL, label="South Island")
for bars in (b1, b2):
    for bar in bars:
        h = bar.get_height()
        if h > 0:
            ax.annotate(f"{h:.0f}", (bar.get_x() + bar.get_width() / 2, h),
                        textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9)
ax.set_xticks(x)
ax.set_xticklabels(years)
ax.set_ylabel("kg CO₂/MWh")
ax.set_title(f"Annual generation-weighted emission factor, NI vs SI ({yr_min}–{yr_max})")
ax.legend(loc="upper right")
fig.tight_layout()
fig.savefig(OUT_DIR / "annual_EF_bar_NI_SI.png", dpi=150)
print("saved annual_EF_bar_NI_SI.png")

# 2: Daily EF, NI vs SI, with 30-day rolling average
fig2, ax2 = plt.subplots(figsize=(16, 5))
for isl, colour in [("NI", NAVY), ("SI", TEAL)]:
    d = daily[daily.island == isl].sort_values("date")
    ax2.plot(d["date"], d["EF_kg_per_MWh"], color=colour, lw=0.5, alpha=0.35, label=f"{isl} daily")
    ax2.plot(d["date"], d["EF_kg_per_MWh"].rolling(30, min_periods=1, center=True).mean(),
              color=colour, lw=2.2, label=f"{isl} 30-day avg")
ax2.set_ylabel("kg CO₂/MWh")
ax2.set_title(f"Daily grid emission factor, NI vs SI ({yr_min}–{yr_max})")
ax2.legend(loc="upper right", fontsize=8, ncol=2)
ax2.grid(alpha=0.3)
fig2.tight_layout()
fig2.savefig(OUT_DIR / "daily_EF_variation_NI_SI.png", dpi=150)
print("saved daily_EF_variation_NI_SI.png")

# 3: Average diurnal EF profile, NI vs SI (mean +/- 1 std band by hour)
fig3, ax3 = plt.subplots(figsize=(11, 6.5))
for isl, colour in [("NI", NAVY), ("SI", TEAL)]:
    h = hourly[hourly.island == isl]
    stats = h.groupby("hour")["EF_kg_per_MWh"].agg(["mean", "std"])
    ax3.plot(stats.index, stats["mean"], color=colour, lw=2.2, marker="o", ms=3, label=f"{isl} mean")
    if isl == "NI":
        ax3.fill_between(stats.index, stats["mean"] - stats["std"], stats["mean"] + stats["std"],
                          color=colour, alpha=0.15)
ax3.set_xlabel("Hour of day (NZ local trading period)")
ax3.set_ylabel("kg CO₂/MWh")
ax3.set_title(f"Average diurnal emission factor profile, NI vs SI ({yr_min}–{yr_max})")
ax3.set_xticks(range(0, 24, 2))
ax3.legend(loc="upper right")
ax3.grid(alpha=0.3)
fig3.tight_layout()
fig3.savefig(OUT_DIR / "hourly_EF_diurnal_profile_NI_SI.png", dpi=150)
print("saved hourly_EF_diurnal_profile_NI_SI.png")

# 4: Generation mix pie charts, NI vs SI, most recent complete year
target_year = fuel_monthly["year"].max()
fy = (
    fuel_monthly[fuel_monthly["year"] == target_year]
    .groupby(["island", "fuel_code"])["gen_mwh"].sum()
    .reset_index()
)

fig4, axes = plt.subplots(1, 2, figsize=(14, 6.5))
for ax, isl in zip(axes, ["NI", "SI"]):
    g = fy[fy.island == isl].sort_values("gen_mwh", ascending=False)
    colours = [FUEL_COLOURS.get(f, "#888888") for f in g["fuel_code"]]
    ax.pie(g["gen_mwh"], labels=g["fuel_code"], autopct="%1.0f%%", colors=colours,
           startangle=90, pctdistance=0.8)
    ax.set_title(f"{isl} — {target_year} generation mix")
fig4.tight_layout()
fig4.savefig(OUT_DIR / f"fuel_mix_share_{target_year}_NI_SI.png", dpi=150)
print(f"saved fuel_mix_share_{target_year}_NI_SI.png")
