"""
Cross-scenario ranking of HVDC transfer-limit violations, for any Assumption-1 template.

Ranks the scenarios by when the required HVDC transfer first exceeds the 1200 MW
link capacity and how fast it grows afterwards. Against the central 2021 template it
reproduces edgs_hvdc_crossscenario_ranking.csv to the displayed precision. The template
is chosen with EDGS_TEMPLATE_YEAR, so the same table can be built for the median-2017
template.

Method:
  demand_2050_twh       = MBIE annual demand target, that scenario, 2050
  first_violation_year  = earliest year in 2024-2050 where max_mw_baseline > 1200 MW
                           (max_mw_baseline = edgs_hvdc_sensitivity_summary's baseline
                           column, i.e. Module 7's own transfer-requirement
                           reimplementation for this template)
  mw_at_first_violation = max_mw_baseline in that first-violation year
  mw_2050                = max_mw_baseline in 2050
  growth_rate_mw_per_yr  = (mw_2050 - mw_at_first_violation) / (2050 - first_violation_year)

Requires edgs_hvdc_sensitivity_summary{SUFFIX}.csv (build_edgs_hvdc_sensitivity.py, same
EDGS_TEMPLATE_YEAR) to already exist for this template.

Outputs: edgs_hvdc_crossscenario_ranking{SUFFIX}.csv
"""
import os
import pandas as pd

from edgs_common import OUT_DIR, SCENARIOS, log_factory

log, lines = log_factory()
HVDC_CAPACITY_MW = 1200.0
TEMPLATE_YEAR = int(os.environ.get("EDGS_TEMPLATE_YEAR", "2021"))
SUFFIX = "" if TEMPLATE_YEAR == 2021 else f"_tmpl{TEMPLATE_YEAR}"
log(f"Template year: {TEMPLATE_YEAR} (suffix '{SUFFIX}')")

targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
hvdc = pd.read_csv(OUT_DIR / f"edgs_hvdc_sensitivity_summary{SUFFIX}.csv")

rows = []
for sc in SCENARIOS:
    t = targets[(targets.scenario == sc) & (targets.year == 2050) & (targets.metric == "annual_demand")]
    demand_2050 = float(t["value"].iloc[0]) if len(t) else float("nan")

    h = hvdc[hvdc.scenario == sc].sort_values("year")
    violated = h[h.max_mw_baseline > HVDC_CAPACITY_MW]
    if len(violated) == 0:
        log(f"  {sc}: never violates under this template, excluded from ranking table")
        continue
    first_row = violated.iloc[0]
    first_year = int(first_row.year)
    mw_first = float(first_row.max_mw_baseline)
    row_2050 = h[h.year == 2050]
    mw_2050 = float(row_2050.max_mw_baseline.iloc[0]) if len(row_2050) else float("nan")
    growth_rate = (mw_2050 - mw_first) / (2050 - first_year) if first_year != 2050 else float("nan")

    rows.append({"scenario": sc, "demand_2050_twh": demand_2050, "first_violation_year": first_year,
                "mw_at_first_violation": mw_first, "mw_2050": mw_2050,
                "growth_rate_mw_per_yr": growth_rate})

df = pd.DataFrame(rows).sort_values("demand_2050_twh", ascending=False)
df.to_csv(OUT_DIR / f"edgs_hvdc_crossscenario_ranking{SUFFIX}.csv", index=False)

log("\n=== Cross-scenario ranking, by 2050 demand (highest to lowest) ===")
log(df.to_string(index=False))

demand_order = list(df.scenario)
fy_order = list(df.sort_values("first_violation_year").scenario)
gr_order = list(df.sort_values("growth_rate_mw_per_yr", ascending=False).scenario)
log(f"\nDemand ranking: {' > '.join(demand_order)}")
log(f"First-violation-year ranking (earliest first): {' < '.join(fy_order)}")
log(f"Growth-rate ranking (steepest first): {' > '.join(gr_order)}")
log(f"Positions where demand ranking and growth-rate ranking match: {sum(a == b for a, b in zip(demand_order, gr_order))}/{len(demand_order)}")
log(f"Positions where demand ranking and first-violation ranking match: {sum(a == b for a, b in zip(demand_order, fy_order))}/{len(demand_order)}")

log(f"\nWrote edgs_hvdc_crossscenario_ranking{SUFFIX}.csv")
(OUT_DIR / f"processing_log_crossscenario_ranking{SUFFIX}.txt").write_text("\n".join(lines), encoding="utf-8")
