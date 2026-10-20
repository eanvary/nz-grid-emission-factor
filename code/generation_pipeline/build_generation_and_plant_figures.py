"""
Generation and per-plant figures (the report and the existing pipeline
outputs are not modified):
  1. Monthly total generation, NI and SI (2015-2025)
  2. Daily total generation, NI and SI (2015-2025)
  3. Fleet-wide per-plant landscape: generation volume, emission intensity
     and total emissions (bubble chart, log generation axis)
  4. Top-15 plants by total generation: output (bars) and emission
     intensity (markers), ranked

Design rationale for (3) and (4), per-plant generation and emissions:
A single bar chart of about 90 plants is not legible. Separate bar charts
for generation and emissions would hide the relationship between them: a
plant's emissions depend on both how much it runs and its emissions per MWh.
A bubble chart shows all three at once, with generation on x, emission factor
(intensity) on y, and bubble area proportional to total emissions. The y
position separates renewables (y=0) from thermal plant. The x position shows
scale of operation. Bubble size shows which plants matter for total emissions;
a small, high-intensity peaker that rarely runs contributes little. A ranked
top-15 bar and marker chart names the largest contributors.
"""
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import sys

ROOT = Path(__file__).parent.parent  # project root: the folder above generation_pipeline/
GEN_DIR = ROOT / "EA_EMI_raw"
NSP_DIR = ROOT / "EA data" / "NSP Tables"
OUT_DIR = ROOT / "output"
sys.path.insert(0, str(Path(__file__).parent))

NAVY = "#1A2744"
TEAL = "#0D7377"
FUEL_COLOURS = {
    "HYD": "#1A6FB5", "GEO": "#A65D2E", "WIN": "#5FB87A",
    "GAS": "#E0A030", "CLG": "#3A3A3A", "DSL": "#B5302E",
    "SOL": "#E8D04A", "WOOD": "#7A5230", "ELE": "#999999",
}
FUEL_LABELS = {
    "HYD": "Hydro", "GEO": "Geothermal", "WIN": "Wind", "GAS": "Gas",
    "CLG": "Coal", "DSL": "Diesel", "SOL": "Solar", "WOOD": "Wood", "ELE": "Other/elec",
}

# 1 and 2: Monthly and daily total generation, NI and SI
# (read from the validated EF pipeline outputs, not recomputed)
monthly = pd.read_csv(OUT_DIR / "monthly_emission_factor_NI_SI.csv", parse_dates=["period"])
daily = pd.read_csv(OUT_DIR / "daily_emission_factor_NI_SI.csv", parse_dates=["date"])

fig, ax = plt.subplots(figsize=(11, 4.5))
for isl, colour in [("NI", NAVY), ("SI", TEAL)]:
    m = monthly[monthly.island == isl].sort_values("period")
    ax.plot(m["period"], m["total_gen_MWh"] / 1000, color=colour, lw=1.3, alpha=0.5, label=f"{isl} monthly")
    ax.plot(m["period"], (m["total_gen_MWh"] / 1000).rolling(12, min_periods=1, center=True).mean(),
            color=colour, lw=2.5, label=f"{isl} 12-mo avg")
ax.set_ylabel("Generation (GWh)")
ax.set_title("Monthly metered generation, NI vs SI (2015–2025)")
ax.legend(loc="upper right", fontsize=8, ncol=2)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT_DIR / "monthly_generation_NI_SI.png", dpi=150)
print("saved monthly_generation_NI_SI.png")

fig2, ax2 = plt.subplots(figsize=(11, 4.5))
for isl, colour in [("NI", NAVY), ("SI", TEAL)]:
    d = daily[daily.island == isl].sort_values("date")
    ax2.plot(d["date"], d["total_gen_MWh"] / 1000, color=colour, lw=0.6, alpha=0.3, label=f"{isl} daily")
    ax2.plot(d["date"], (d["total_gen_MWh"] / 1000).rolling(30, min_periods=1, center=True).mean(),
              color=colour, lw=2, label=f"{isl} 30-day avg")
ax2.set_ylabel("Generation (GWh)")
ax2.set_title("Daily metered generation, NI vs SI (2015–2025)")
ax2.legend(loc="upper right", fontsize=8, ncol=2)
ax2.grid(alpha=0.3)
fig2.tight_layout()
fig2.savefig(OUT_DIR / "daily_generation_NI_SI.png", dpi=150)
print("saved daily_generation_NI_SI.png")

# Rebuild per-(POC, fuel) totals over the full period, joined to plant identity, for the
# per-plant figures. Generation, fills and factors come from the shared
# attribution module (fuel_attribution.py): generator-level factors, Huntly coal/gas split,
# flagged fills (Huntly Sep 2020, norskeskog 2015-2019, Matahina Oct 2021-Dec 2025), so the
# totals equal the EF pipeline's. Plant names come from the module's register copy; this
# script does not read the register itself.
from fuel_attribution import FuelAttribution, poc_island_map  # noqa: E402

fa = FuelAttribution()
poc_island = poc_island_map()


def base_name(name):
    # "Huntly Rankine 1" to "Huntly Rankine 4" become "Huntly Rankine"; "Huntly 5" and "Huntly 6" become "Huntly"
    return re.sub(r"\s*\d+$", "", str(name)).strip()


reg = fa.reg.copy()
reg["base_plant_name"] = reg["PlantName"].map(base_name)
# Keyed by (POC, fuel), not POC alone: Huntly HLY2201 hosts coal "Huntly Rankine 1-4" and gas
# "Huntly 5/6"; the key uses the metered fuel before the coal/gas split.
poc_fuel_to_plant = (
    reg.groupby(["PointOfConnectionCode", "FuelCode"])["base_plant_name"].agg(lambda s: s.mode().iat[0]).to_dict()
)

# fallback by POC alone where the metered fuel differs from the register's (Kinleith: metered Wood, register GAS)
poc_to_plant = reg.groupby("PointOfConnectionCode")["base_plant_name"].agg(lambda s: s.mode().iat[0]).to_dict()

gen = fa.generation("month")
gen["island"] = gen["poc"].map(poc_island)
gen = gen[gen["island"].isin(["NI", "SI"])].copy()
gen["fuel_metered"] = gen["fuel_std"]
gen = fa.attribute(gen)
gen["ef_kg_per_mwh"] = gen["ef_kg_per_mwh"].astype(float)
gen["plant_name"] = [
    poc_fuel_to_plant.get((p, fu), poc_to_plant.get(p, f"{p} ({fu})")) for p, fu in zip(gen["poc"], gen["fuel_metered"])
]

plant_totals = (
    gen.groupby(["plant_name", "poc", "fuel_std", "island"])
    .agg(total_gen_MWh=("gen_mwh", "sum"), total_CO2_kg=("co2_kg", "sum"))
    .reset_index()
)
plant_totals["EF_kg_per_MWh"] = plant_totals["total_CO2_kg"] / plant_totals["total_gen_MWh"]

# One bubble per (plant, fuel). A few plants have more than one POC (e.g.
# Manapouri and Roxburgh extensions); Huntly's 2 gas units already share one POC.
plant_agg = (
    plant_totals.groupby(["plant_name", "fuel_std", "island"])
    .agg(total_gen_MWh=("total_gen_MWh", "sum"), total_CO2_kg=("total_CO2_kg", "sum"))
    .reset_index()
)
plant_agg["EF_kg_per_MWh"] = plant_agg["total_CO2_kg"] / plant_agg["total_gen_MWh"]
plant_agg["total_CO2_kt"] = plant_agg["total_CO2_kg"] / 1e6
plant_agg["total_gen_GWh"] = plant_agg["total_gen_MWh"] / 1000

plant_agg.to_csv(OUT_DIR / "plant_level_generation_emissions_2015_2025.csv", index=False)
print(f"saved plant_level_generation_emissions_2015_2025.csv ({len(plant_agg)} plant x fuel rows, "
      f"{plant_agg['total_gen_MWh'].sum()/1e6:.2f} TWh total)")

# 3: Fleet-wide bubble chart: generation, intensity and total emissions
fig3, ax3 = plt.subplots(figsize=(10, 6.5))
size_scale = 4000 / plant_agg["total_CO2_kt"].max()
fuel_order = ["HYD", "WIN", "SOL", "GEO", "GAS", "CLG", "DSL", "WOOD", "ELE"]
for fuel in [f for f in fuel_order if f in plant_agg["fuel_std"].unique()]:
    g = plant_agg[plant_agg["fuel_std"] == fuel]
    size = 25 + g["total_CO2_kt"] * size_scale
    ax3.scatter(g["total_gen_GWh"], g["EF_kg_per_MWh"], s=size,
                color=FUEL_COLOURS.get(fuel, "#888888"), alpha=0.6,
                edgecolors="white", linewidths=0.6)

# Fixed-size proxy handles for the legend: plotted bubble sizes span 2 orders
# of magnitude and would make the legend swatches unreadable.
legend_handles = [
    plt.scatter([], [], s=80, color=FUEL_COLOURS[f], edgecolors="white", linewidths=0.6, label=FUEL_LABELS[f])
    for f in fuel_order if f in plant_agg["fuel_std"].unique()
]
ax3.legend(handles=legend_handles, loc="upper left", fontsize=8, framealpha=0.9, title="Fuel")

# Labels go only on the largest emitters (thermal) and the largest generators
# (renewables), with small manual y-offsets to reduce overlap between adjacent points.
top_emit = plant_agg.nlargest(5, "total_CO2_kt")
top_gen = plant_agg.nlargest(3, "total_gen_GWh")
labelled = pd.concat([top_emit, top_gen]).drop_duplicates(subset=["plant_name", "fuel_std"])
labelled = labelled.sort_values("total_gen_GWh")
for i, (_, r) in enumerate(labelled.iterrows()):
    y_off = 8 if i % 2 == 0 else -12
    ax3.annotate(r["plant_name"], (r["total_gen_GWh"], r["EF_kg_per_MWh"]),
                 fontsize=7.5, xytext=(6, y_off), textcoords="offset points")

ax3.set_xscale("log")
ax3.set_xlabel("Total generation, 2015–2025 (GWh, log scale)")
ax3.set_ylabel("Average emission factor (kg CO₂/MWh)")
ax3.set_title("Fleet-wide plant landscape: output vs emission intensity\n(bubble area ∝ total CO₂ emitted, 2015–2025)")
ax3.set_ylim(-60, max(plant_agg["EF_kg_per_MWh"].max() * 1.08, 100))
ax3.grid(alpha=0.3, which="both")
fig3.tight_layout()
fig3.savefig(OUT_DIR / "plant_landscape_generation_vs_intensity.png", dpi=150)
print("saved plant_landscape_generation_vs_intensity.png")

# 4: Top-15 plants by generation: bars (generation) and markers (EF)
top15 = (
    plant_agg.groupby("plant_name")
    .agg(total_gen_GWh=("total_gen_GWh", "sum"), total_CO2_kt=("total_CO2_kt", "sum"))
    .reset_index()
)
top15["EF_kg_per_MWh"] = top15["total_CO2_kt"] * 1e6 / (top15["total_gen_GWh"] * 1000)
dominant_fuel = (
    plant_agg.sort_values("total_gen_GWh", ascending=False)
    .drop_duplicates(subset=["plant_name"])[["plant_name", "fuel_std"]]
)
top15 = top15.merge(dominant_fuel, on="plant_name").nlargest(15, "total_gen_GWh").sort_values("total_gen_GWh")

fig4, ax4 = plt.subplots(figsize=(9, 6.5))
colors = [FUEL_COLOURS.get(f, "#888888") for f in top15["fuel_std"]]
bars = ax4.barh(top15["plant_name"], top15["total_gen_GWh"], color=colors)
ax4.set_xlabel("Total generation, 2015–2025 (GWh)")
ax4.set_title("Top 15 plants by total generation: output and emission intensity")

ax4b = ax4.twiny()
ax4b.scatter(top15["EF_kg_per_MWh"], top15["plant_name"], color="black", marker="D", s=35, zorder=5,
             label="Emission factor (kg CO₂/MWh)")
ax4b.set_xlabel("Emission factor (kg CO₂/MWh, ◆ markers)")

handles = [plt.Rectangle((0, 0), 1, 1, color=FUEL_COLOURS[f]) for f in ["HYD", "GEO", "WIN", "GAS", "CLG"]]
labels = [FUEL_LABELS[f] for f in ["HYD", "GEO", "WIN", "GAS", "CLG"]]
handles.append(plt.Line2D([0], [0], marker="D", color="black", linestyle="None", markersize=6))
labels.append("Emission factor")
ax4.legend(handles, labels, loc="lower right", fontsize=8)
fig4.tight_layout()
fig4.savefig(OUT_DIR / "top15_plants_generation_and_intensity.png", dpi=150)
print("saved top15_plants_generation_and_intensity.png")
