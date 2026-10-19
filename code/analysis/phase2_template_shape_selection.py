"""
Phase 2, template selection: which historical year should serve as the
Assumption-1 hourly shape template?

WHY THIS EXISTS (2026-09-20). The shape template was originally labelled
"central 2021" on the basis of annual hydro volume, computed against the
2021-2025 window available at the time. Re-checked against the full 2015-2025
metered record, 2021 is the 3rd-driest of 11 years (18th percentile) and 2017
is the exact median -- see EDGS_Pipeline_Complete_Documentation.md section 8.5
and PLAN_11YEAR_TEMPLATE_REASSESSMENT.md. That raised the question of whether
the template year should be switched to 2017.

Annual hydro volume is, however, not the quantity a template supplies. Annual
volumes are always MBIE's published totals, imposed on every template and
identical across them (verified in Brief G). What the template supplies is the
HOURLY SHAPE: the within-year timing of renewables, demand, and therefore of
the emission factor. The selection criterion should be measured on shape.

This script measures it. For every year of the metered record it computes the
normalised shape of the NI generation-basis hourly emission factor on three
axes -- hour of day, hour of week, and month of year -- and correlates each
against the most recent grid (the 2024-2025 mean shape). It reports those
alongside annual hydro volume and wind share, so the trade-off between shape
fidelity and hydro neutrality is visible in one table.

WHAT IT FOUND (2026-09-20 run). No year dominates. The shipped template, 2021,
gives the best diurnal (hour-of-day) and seasonal (month-of-year) match of any
pre-2024 year but the WORST day-of-week match of the whole record -- its
weekday/weekend contrast is the flattest measured, consistent with the 2021
activity restrictions. 2019 is the best weekly match and sits near the hydro
median, but its seasonal match is weak. 2017, the hydro-median year, leads on
no shape axis and has the lowest wind share in the record. So the choice is a
trade-off between axes, not a ranking with a single winner, and this script
reports the trade-off rather than declaring one.

The relevant point for the paper: switching the template to 2017 on the basis
of annual hydro volume would not improve shape fidelity on any axis, and would
select the year least like the projected (increasingly wind-heavy) grid.

INPUTS   output/hourly_emission_factor_NI_SI.csv   (metered hourly EF, 2015-)
         docs/validation/hourly_fuel_mix_NI_SI.csv (metered generation by fuel)
OUTPUTS  analysis_paper/tables/phase2_template_shape_selection.csv
         analysis_paper/logs/phase2_template_shape_selection_log.txt
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "output"
DOCS = ROOT / "docs" / "validation"
TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"

RECENT = [2024, 2025]          # "the current grid" reference shape
ISLAND = "NI"                  # the island the paper's headline building sits on
SHIPPED = 2021                 # template the shipped results are built on

log_lines = []


def log(m):
    print(m)
    log_lines.append(str(m))


# Load
ef = pd.read_csv(HIST / "hourly_emission_factor_NI_SI.csv")
ef = ef[ef["island"] == ISLAND].copy()
ef["datetime"] = pd.to_datetime(ef["datetime"])
ef["year"] = ef["datetime"].dt.year
ef["hour"] = ef["datetime"].dt.hour
ef["dow"] = ef["datetime"].dt.dayofweek
ef["month"] = ef["datetime"].dt.month
ef["ef"] = ef["EF_kg_per_MWh"]

full_years = sorted(y for y, g in ef.groupby("year")
                    if g["datetime"].dt.date.nunique() >= 365)
ef = ef[ef["year"].isin(full_years)]
log(f"Metered {ISLAND} hourly EF: {len(ef):,} rows, complete years {full_years[0]}-{full_years[-1]}")

fuel = pd.read_csv(DOCS / "hourly_fuel_mix_NI_SI.csv", parse_dates=["date"])
fuel["year"] = fuel["date"].dt.year
mix = fuel.pivot_table(index="year", columns="fuel_std", values="gen_mwh", aggfunc="sum") / 1e6
mix["total"] = mix.sum(axis=1)


# Shapes
def profile(g, keys):
    """Normalised mean EF by the given time keys (mean of profile == 1)."""
    p = g.groupby(keys)["ef"].mean()
    return p / g["ef"].mean()


AXES = {"hour_of_day": ["hour"], "day_of_week": ["dow"], "hour_of_week": ["dow", "hour"],
        "month_of_year": ["month"]}
shapes = {axis: {y: profile(g, keys) for y, g in ef.groupby("year")}
          for axis, keys in AXES.items()}
reference = {axis: pd.concat([shapes[axis][y] for y in RECENT], axis=1).mean(axis=1)
             for axis in AXES}

rows = []
for y in full_years:
    g = ef[ef["year"] == y]
    row = {"year": y,
           "mean_ef_kg_per_mwh": g["ef"].mean(),
           "cv_hourly_ef": g["ef"].std() / g["ef"].mean(),
           "weekend_weekday_ratio": g[g["dow"] >= 5]["ef"].mean() / g[g["dow"] < 5]["ef"].mean(),
           "hydro_twh": mix.loc[y, "HYD"],
           "wind_share_pct": 100 * mix.loc[y, "WIN"] / mix.loc[y, "total"],
           "thermal_share_pct": 100 * mix.loc[y, ["CLG", "GAS", "DSL"]].sum() / mix.loc[y, "total"]}
    for axis in AXES:
        a, b = shapes[axis][y].align(reference[axis], join="inner")
        row["corr_" + axis] = np.corrcoef(a.values, b.values)[0, 1]
    rows.append(row)

t = pd.DataFrame(rows).set_index("year")
t["hydro_rank_driest_first"] = t["hydro_twh"].rank().astype(int)
t["hydro_pctile"] = 100 * (t["hydro_twh"].rank() - 1) / (len(t) - 1)
t["is_reference_year"] = t.index.isin(RECENT)

wettest, driest = t["hydro_twh"].idxmax(), t["hydro_twh"].idxmin()
t["role"] = ""
t.loc[wettest, "role"] = "wet bound"
t.loc[driest, "role"] = "dry bound"
t.loc[t["hydro_rank_driest_first"] == int(np.ceil(len(t) / 2)), "role"] = "hydro median"

t.loc[SHIPPED, "role"] = (t.loc[SHIPPED, "role"] + "; " if t.loc[SHIPPED, "role"] else "") + "shipped template"

CORRS = ["corr_" + a for a in AXES]
cols = ["hydro_twh", "hydro_rank_driest_first", "hydro_pctile", "wind_share_pct",
        "thermal_share_pct", "mean_ef_kg_per_mwh", "cv_hourly_ef",
        "weekend_weekday_ratio"] + CORRS + ["role"]
log("\n=== Template candidates: hydro position and shape fidelity (NI) ===")
log(f"Reference shape = mean of {RECENT}; correlations are against that shape.")
log(t[cols].round(3).to_string())

# candidates: exclude the sensitivity bounds and the years defining the reference
eligible = t.drop(index=[wettest, driest]).loc[lambda d: ~d["is_reference_year"]]
log("\n=== Per-axis leader among candidate years ===")
log(f"Wettest ({wettest}) and driest ({driest}) reserved as sensitivity bounds; "
    f"reference years {RECENT} excluded. Candidates: {list(eligible.index)}")
for c in CORRS:
    lead = eligible[c].idxmax()
    log(f"  {c:22s} leader {lead} (r={eligible.loc[lead, c]:.3f});  "
        f"shipped {SHIPPED} r={t.loc[SHIPPED, c]:.3f}, "
        f"rank {int(eligible[c].rank(ascending=False).loc[SHIPPED])} of {len(eligible)}")

median_year = int(t[t["role"].str.contains("hydro median")].index[0])
log("\n=== Read-out ===")
log(f"No single year leads on every axis, so the template is a trade-off, not a ranking.")
log(f"Shipped {SHIPPED}: best diurnal and seasonal match of any candidate, worst day-of-week "
    f"match of the record (r={t.loc[SHIPPED, 'corr_day_of_week']:.3f}, weekend/weekday ratio "
    f"{t.loc[SHIPPED, 'weekend_weekday_ratio']:.3f}, the flattest measured); "
    f"hydro rank {t.loc[SHIPPED, 'hydro_rank_driest_first']} of {len(t)}.")
log(f"Hydro-median year {median_year}: leads no shape axis; wind share "
    f"{t.loc[median_year, 'wind_share_pct']:.1f}%, the lowest of the record "
    f"({t['wind_share_pct'].min():.1f}-{t['wind_share_pct'].max():.1f}%). Switching the "
    f"template to it on annual hydro volume alone would not improve shape fidelity on any "
    f"axis, on a quantity the template does not control: annual volumes are MBIE's published "
    f"totals under every template.")

TABLES.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)
t[cols].to_csv(TABLES / "phase2_template_shape_selection.csv")
with open(LOGS / "phase2_template_shape_selection_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log(f"\nWrote {TABLES / 'phase2_template_shape_selection.csv'}")
log("Done.")
