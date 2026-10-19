"""
Phase 3, template robustness: does the spatial > temporal ranking survive a
change of Assumption-1 shape template?

Why this check. The paper's decomposition uses the central template (2021).
The hydro-template sensitivity covers the annual EF trajectory, not the
decomposition, so whether the ranking depends on the template needs its own
test. This script compares phase3_decomposition_full.csv (central 2021)
with the _tmpl2023 (wet), _tmpl2024 (dry) and _tmpl2017 (hydro-median) runs
produced by `EDGS_TEMPLATE_YEAR=<year> python phase3_decomposition.py`.

All four inputs are built with the same pipeline code, including the observed
solar shape for templates without solar data and the weekday alignment of
templates, so the comparison is like-for-like.

Outputs  analysis_paper/tables/phase3_template_ranking_check.csv
         analysis_paper/logs/phase3_template_ranking_check_log.txt
"""
import numpy as np
import pandas as pd
from pathlib import Path

TABLES = Path(__file__).resolve().parents[1] / "tables"
LOGS = Path(__file__).resolve().parents[1] / "logs"

TEMPLATES = {"central_2021": "", "wet_2023": "_tmpl2023",
             "dry_2024": "_tmpl2024", "median_2017": "_tmpl2017"}
HEADLINE = dict(scenario="Reference", start_year=2025,
                study_period_yrs_requested=25, load_shape="daytime_office")

log_lines = []


def log(m):
    print(m)
    log_lines.append(str(m))


rows = []
for label, suffix in TEMPLATES.items():
    d = pd.read_csv(TABLES / f"phase3_decomposition_full{suffix}.csv")
    prim = (d["spatial_component"].abs() > d["temporal_component"].abs())
    alt = (d["spatial_alt_component"].abs() > d["temporal_alt_component"].abs())
    ratio_prim = (d["spatial_component"].abs() / d["temporal_component"].abs()).replace(np.inf, np.nan)
    ratio_alt = (d["spatial_alt_component"].abs() / d["temporal_alt_component"].abs()).replace(np.inf, np.nan)
    hl = d
    for k, v in HEADLINE.items():
        hl = hl[hl[k] == v]
    hl = hl.iloc[0] if len(hl) else None
    rows.append({
        "template": label,
        "n_rows": len(d),
        "spatial_gt_temporal_primary": int(prim.sum()),
        "spatial_gt_temporal_alt": int(alt.sum()),
        "ratio_min_primary": ratio_prim.min(),
        "ratio_median_primary": ratio_prim.median(),
        "ratio_min_alt": ratio_alt.min(),
        "headline_total_error_pct": None if hl is None else hl["total_error_pct_of_Ea"],
        "headline_spatial": None if hl is None else hl["spatial_component"],
        "headline_temporal": None if hl is None else hl["temporal_component"],
        "headline_trajectory": None if hl is None else hl["trajectory_component"],
        "headline_sign_of_total": None if hl is None else np.sign(hl["total_error_d_minus_a"]),
    })

t = pd.DataFrame(rows).set_index("template")
log("=== Spatial vs temporal ranking under each Assumption-1 shape template ===")
log(f"Headline row = {HEADLINE}")
log(t.round(3).to_string())

log("\n=== Read-out ===")
holds_prim = (t["spatial_gt_temporal_primary"] == t["n_rows"]).all()
holds_alt = (t["spatial_gt_temporal_alt"] == t["n_rows"]).all()
log(f"Spatial exceeds temporal in every row, every template, primary order: {holds_prim}")
log(f"Same under the alternative (spatial-first) order: {holds_alt}")
log(f"Smallest spatial:temporal ratio across all templates, primary order: "
    f"{t['ratio_min_primary'].min():.2f} ({t['ratio_min_primary'].idxmin()}); "
    f"alternative order: {t['ratio_min_alt'].min():.2f} ({t['ratio_min_alt'].idxmin()})")
signs = t["headline_sign_of_total"].unique()
log(f"Headline total-error sign identical across templates: {len(signs) == 1} (sign {signs})")
log(f"Headline total error ranges {t['headline_total_error_pct'].min():.1f}% to "
    f"{t['headline_total_error_pct'].max():.1f}% of the resolved value across templates "
    f"(central {t.loc['central_2021', 'headline_total_error_pct']:.1f}%).")

t.to_csv(TABLES / "phase3_template_ranking_check.csv")
with open(LOGS / "phase3_template_ranking_check_log.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))
log(f"\nWrote {TABLES / 'phase3_template_ranking_check.csv'}")
