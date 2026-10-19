import numpy as np
import pandas as pd
from pathlib import Path

TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"
log_lines = []
def log(m):
    print(m); log_lines.append(str(m))

annual = pd.read_csv(TABLES / "phase1_annual_trajectory_projected.csv")
gen_side = annual[annual["ef_basis"] == "generation"].copy()

log("=== NI-ONLY data-driven percentile thresholds (SI excluded: trivially ~0 all "
    "years, no thermal fleet -- see Phase 0) ===")
ni = gen_side[gen_side["island"] == "NI"]["gen_weighted_mean_ef"].dropna()
pcts = {p: ni.quantile(p / 100) for p in [75, 50, 25, 10, 5]}
log(f"NI-only pooled percentile values (kg/kWh): { {k: round(v,5) for k,v in pcts.items()} }")

rows = []
for scen, g in gen_side[gen_side["island"] == "NI"].groupby("scenario"):
    g = g.sort_values("year")
    row = {"scenario": scen}
    for p, thresh in pcts.items():
        below = g[g["gen_weighted_mean_ef"] <= thresh]
        row[f"first_year_below_p{p}_NIonly"] = int(below["year"].min()) if len(below) else None
    rows.append(row)
df = pd.DataFrame(rows).sort_values("scenario")
log(df.to_string(index=False))
df.to_csv(TABLES / "phase1_percentile_crossing_years_NIonly.csv", index=False)

log("\nSI note: South Island generation-side EF is at/near its floor (~0 kg/kWh) "
    "from 2024 in every scenario -- there is no meaningful percentile-crossing "
    "dynamic to report for SI on the generation side; this is a real structural "
    "feature (no thermal fleet), not a data gap. SI is only dynamically interesting "
    "on the CONSUMPTION side (see phase1_spatial.py).")

with open(LOGS / "phase1_trajectories_fix_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
