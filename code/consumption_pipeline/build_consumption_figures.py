"""
Figures for the consumption-based NI/SI emission factor database.
The set matches the generation-side figures, for consumption volume and
consumption-based emission factor.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "output"

NAVY = "#1A2744"
TEAL = "#0D7377"
GOLD = "#C9A227"

monthly = pd.read_csv(OUT_DIR / "monthly_consumption_EF_NI_SI.csv", parse_dates=["period"])
daily = pd.read_csv(OUT_DIR / "daily_consumption_EF_NI_SI.csv", parse_dates=["date"])
hourly = pd.read_csv(OUT_DIR / "hourly_consumption_EF_NI_SI.csv", parse_dates=["datetime"])

# Figure 1: Monthly consumption volume, NI and SI
fig, ax = plt.subplots(figsize=(11, 4.5))
ax.plot(monthly["period"], monthly["NI_consumption_MWh"] / 1000, color=NAVY, lw=1.3, alpha=0.5, label="NI monthly")
ax.plot(monthly["period"], (monthly["NI_consumption_MWh"] / 1000).rolling(12, min_periods=1, center=True).mean(),
        color=NAVY, lw=2.5, label="NI 12-mo avg")
ax.plot(monthly["period"], monthly["SI_consumption_MWh"] / 1000, color=TEAL, lw=1.3, alpha=0.5, label="SI monthly")
ax.plot(monthly["period"], (monthly["SI_consumption_MWh"] / 1000).rolling(12, min_periods=1, center=True).mean(),
        color=TEAL, lw=2.5, label="SI 12-mo avg")
ax.set_ylabel("Consumption (GWh)")
ax.set_title("Monthly apparent electricity consumption, NI vs SI (2015–2025)")
ax.legend(loc="upper right", fontsize=8, ncol=2)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "monthly_consumption_volume_NI_SI.png", dpi=150)
print("saved monthly_consumption_volume_NI_SI.png")

# Figure 2: Daily consumption volume, NI and SI
fig2, ax2 = plt.subplots(figsize=(11, 4.5))
ax2.plot(daily["date"], daily["NI_consumption_MWh"] / 1000, color=NAVY, lw=0.6, alpha=0.3, label="NI daily")
ax2.plot(daily["date"], (daily["NI_consumption_MWh"] / 1000).rolling(30, min_periods=1, center=True).mean(),
         color=NAVY, lw=2, label="NI 30-day avg")
ax2.plot(daily["date"], daily["SI_consumption_MWh"] / 1000, color=TEAL, lw=0.6, alpha=0.3, label="SI daily")
ax2.plot(daily["date"], (daily["SI_consumption_MWh"] / 1000).rolling(30, min_periods=1, center=True).mean(),
         color=TEAL, lw=2, label="SI 30-day avg")
ax2.set_ylabel("Consumption (GWh)")
ax2.set_title("Daily apparent electricity consumption, NI vs SI (2015–2025)")
ax2.legend(loc="upper right", fontsize=8, ncol=2)
ax2.grid(alpha=0.3)
fig2.tight_layout()
fig2.savefig(OUT_DIR / "daily_consumption_volume_NI_SI.png", dpi=150)
print("saved daily_consumption_volume_NI_SI.png")

# Figure 3: Monthly consumption-based and generation-based EF, NI and SI
fig3, (ax3a, ax3b) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
ax3a.plot(monthly["period"], monthly["NI_EF_generation"], color="#9098A8", lw=1.2, alpha=0.6, label="NI generation-based EF")
ax3a.plot(monthly["period"], monthly["NI_EF_consumption"], color=NAVY, lw=2, label="NI consumption-based EF")
ax3a.set_ylabel("kg CO₂/MWh")
ax3a.set_title("North Island: generation-based vs consumption-based monthly emission factor")
ax3a.legend(loc="upper right", fontsize=8)
ax3a.grid(alpha=0.3)

ax3b.plot(monthly["period"], monthly["SI_EF_generation"], color="#7FBFC2", lw=1.2, alpha=0.6, label="SI generation-based EF (= 0)")
ax3b.plot(monthly["period"], monthly["SI_EF_consumption"], color=TEAL, lw=2, label="SI consumption-based EF")
ax3b.set_ylabel("kg CO₂/MWh")
ax3b.set_title("South Island: generation-based vs consumption-based monthly emission factor")
ax3b.legend(loc="upper right", fontsize=8)
ax3b.grid(alpha=0.3)
fig3.tight_layout()
fig3.savefig(OUT_DIR / "monthly_consumption_vs_generation_EF_NI_SI.png", dpi=150)
print("saved monthly_consumption_vs_generation_EF_NI_SI.png")

# Figure 4: Daily consumption-based EF, NI and SI
fig4, ax4 = plt.subplots(figsize=(11, 4.5))
ax4.plot(daily["date"], daily["NI_EF_consumption"], color=NAVY, lw=0.6, alpha=0.3, label="NI daily")
ax4.plot(daily["date"], daily["NI_EF_consumption"].rolling(30, min_periods=1, center=True).mean(),
         color=NAVY, lw=2, label="NI 30-day avg")
ax4.plot(daily["date"], daily["SI_EF_consumption"], color=TEAL, lw=0.6, alpha=0.3, label="SI daily")
ax4.plot(daily["date"], daily["SI_EF_consumption"].rolling(30, min_periods=1, center=True).mean(),
         color=TEAL, lw=2, label="SI 30-day avg")
ax4.set_ylabel("kg CO₂/MWh")
ax4.set_title("Daily consumption-based emission factor, NI vs SI (2015–2025)")
ax4.legend(loc="upper right", fontsize=8, ncol=2)
ax4.grid(alpha=0.3)
fig4.tight_layout()
fig4.savefig(OUT_DIR / "daily_consumption_EF_NI_SI.png", dpi=150)
print("saved daily_consumption_EF_NI_SI.png")

# Figure 5: Hourly (diurnal) consumption-based EF profile, NI and SI
prof = hourly.groupby("hour")[["NI_EF_consumption", "SI_EF_consumption"]].agg(["mean", "std"])
fig5, ax5 = plt.subplots(figsize=(7.5, 4.5))
ax5.plot(prof.index, prof[("NI_EF_consumption", "mean")], color=NAVY, lw=2, marker="o", ms=3, label="NI mean")
ax5.fill_between(prof.index, prof[("NI_EF_consumption", "mean")] - prof[("NI_EF_consumption", "std")],
                  prof[("NI_EF_consumption", "mean")] + prof[("NI_EF_consumption", "std")], color=NAVY, alpha=0.15)
ax5.plot(prof.index, prof[("SI_EF_consumption", "mean")], color=TEAL, lw=2, marker="o", ms=3, label="SI mean")
ax5.fill_between(prof.index, prof[("SI_EF_consumption", "mean")] - prof[("SI_EF_consumption", "std")],
                  prof[("SI_EF_consumption", "mean")] + prof[("SI_EF_consumption", "std")], color=TEAL, alpha=0.15)
ax5.set_xlabel("Hour of day (NZ local trading period)")
ax5.set_ylabel("kg CO₂/MWh")
ax5.set_title("Average diurnal consumption-based emission factor profile, NI vs SI (2015–2025)")
ax5.set_xticks(range(0, 24, 2))
ax5.legend(loc="upper right", fontsize=8)
ax5.grid(alpha=0.3)
fig5.tight_layout()
fig5.savefig(OUT_DIR / "hourly_consumption_EF_diurnal_profile_NI_SI.png", dpi=150)
print("saved hourly_consumption_EF_diurnal_profile_NI_SI.png")

# Figure 6: Annual bar comparison: consumption-based EF, NI and SI
annual = pd.read_csv(OUT_DIR / "annual_consumption_EF_NI_SI.csv")
years = annual["year"].tolist()
fig6, ax6 = plt.subplots(figsize=(7, 4))
x = range(len(years))
w = 0.38
ax6.bar([i - w / 2 for i in x], annual["NI_EF_consumption"], width=w, color=NAVY, label="North Island")
ax6.bar([i + w / 2 for i in x], annual["SI_EF_consumption"], width=w, color=TEAL, label="South Island")
ax6.set_xticks(list(x))
ax6.set_xticklabels(years)
ax6.set_ylabel("kg CO₂/MWh")
ax6.set_title("Annual consumption-based emission factor, NI vs SI (2015–2025)")
ax6.legend(frameon=False)
ax6.grid(axis="y", alpha=0.3)
for i, y in enumerate(years):
    ax6.text(i - w / 2, annual["NI_EF_consumption"].iloc[i] + 4, f"{annual['NI_EF_consumption'].iloc[i]:.0f}", ha="center", fontsize=8)
    ax6.text(i + w / 2, annual["SI_EF_consumption"].iloc[i] + 4, f"{annual['SI_EF_consumption'].iloc[i]:.1f}", ha="center", fontsize=7)
fig6.tight_layout()
fig6.savefig(OUT_DIR / "annual_consumption_EF_bar_NI_SI.png", dpi=150)
print("saved annual_consumption_EF_bar_NI_SI.png")
