"""
Phase 2, template selection, robustness check: 2025 alone as the yardstick.

WHY THIS EXISTS (2026-09-27). phase2_template_shape_selection.py scores each
candidate year's timing against the mean of metered 2024 and 2025. That makes
2024 and 2025 ineligible as templates, since a year scored against itself wins
by construction. Raised in supervision prep: if recent years are good enough
to be the reference, why not use one as the template?

This re-runs the identical method with 2025 alone as the yardstick, so 2024
becomes an eligible candidate and can be compared with 2021 on equal terms.
Nothing shipped is overwritten.

Method, unchanged from the shipped script: for each complete metered year,
normalise the NI generation-basis hourly EF by that year's mean, average it by
hour of day, day of week, hour of week and month of year, and correlate each
profile with the yardstick year's profile.

INPUTS   output/hourly_emission_factor_NI_SI.csv (metered hourly EF, EA/EMI)
OUTPUTS  analysis_paper/tables/phase2_template_yardstick2025.csv
         analysis_paper/logs/phase2_template_yardstick2025_log.txt
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"
YARDSTICK = [2025]
ISLAND = "NI"
SHIPPED = 2021

lines = []
def log(m):
    print(m); lines.append(str(m))

ef = pd.read_csv(ROOT / "output" / "hourly_emission_factor_NI_SI.csv")
ef = ef[ef["island"] == ISLAND].copy()
ef["datetime"] = pd.to_datetime(ef["datetime"])
ef["year"] = ef["datetime"].dt.year
ef["hour"] = ef["datetime"].dt.hour
ef["dow"] = ef["datetime"].dt.dayofweek
ef["month"] = ef["datetime"].dt.month
ef["ef"] = ef["EF_kg_per_MWh"]
full = sorted(y for y, g in ef.groupby("year") if g["datetime"].dt.date.nunique() >= 365)
ef = ef[ef["year"].isin(full)]


def profile(g, keys):
    p = g.groupby(keys)["ef"].mean()
    return p / g["ef"].mean()


AXES = {"hour_of_day": ["hour"], "day_of_week": ["dow"], "hour_of_week": ["dow", "hour"],
        "month_of_year": ["month"]}
shapes = {a: {y: profile(g, k) for y, g in ef.groupby("year")} for a, k in AXES.items()}
ref = {a: pd.concat([shapes[a][y] for y in YARDSTICK], axis=1).mean(axis=1) for a in AXES}

rows = []
for y in full:
    if y in YARDSTICK:
        continue
    r = {"year": y}
    for a in AXES:
        x, z = shapes[a][y].align(ref[a], join="inner")
        r["corr_" + a] = np.corrcoef(x.values, z.values)[0, 1]
    rows.append(r)
t = pd.DataFrame(rows).set_index("year")
C = ["corr_" + a for a in AXES]
t["mean_rank"] = t[C].rank(ascending=False).mean(axis=1)

log(f"Yardstick: metered {ISLAND} {YARDSTICK} alone. Candidates: {list(t.index)}")
log(t.round(3).to_string())
log("\nPer-axis leader (all candidates, 2024 included):")
for c in C:
    lead = t[c].idxmax()
    log(f"  {c:22s} leader {lead} r={t.loc[lead, c]:.3f} | 2021 r={t.loc[SHIPPED, c]:.3f} "
        f"rank {int(t[c].rank(ascending=False)[SHIPPED])} | 2024 r={t.loc[2024, c]:.3f} "
        f"rank {int(t[c].rank(ascending=False)[2024])} | 2017 r={t.loc[2017, c]:.3f}")
log("\nMean rank across the four axes (1 = best):")
log(t["mean_rank"].sort_values().round(2).to_string())

t.to_csv(TABLES / "phase2_template_yardstick2025.csv")
(LOGS / "phase2_template_yardstick2025_log.txt").write_text("\n".join(lines), encoding="utf-8")
