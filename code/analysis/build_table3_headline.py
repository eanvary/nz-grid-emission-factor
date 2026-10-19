"""
Table 3 -- headline results. Restricted to the rows a reader needs: the
headline case, the three demand profiles at the headline trajectory/start
year, and one row per trajectory at the headline profile/start year. The
full 120-row table stays in supplementary (phase4_table1_full_decomposition.csv).
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"

decomp = pd.read_csv(TABLES / "phase3_decomposition_contextualised_v3_finalEUI.csv")

# Updated at the user's request to the longest non-truncated ('full')
# period available -- there is no literal 27-year row (start years in the
# data are only 2025, 2027, 2030); 2025+25yr is the closest full-fit
# approximation to the whole modelled horizon. Was 2027/10yr.
HEADLINE_PROFILE, HEADLINE_TRAJECTORY, HEADLINE_START, HEADLINE_PERIOD = "daytime_office", "Reference", 2025, 25
profiles = sorted(decomp["load_shape"].unique())
trajectories = sorted(decomp["scenario"].unique())

profile_rows = decomp[(decomp["load_shape"].isin(profiles)) & (decomp["scenario"] == HEADLINE_TRAJECTORY) &
                       (decomp["start_year"] == HEADLINE_START) & (decomp["study_period_yrs_requested"] == HEADLINE_PERIOD)]
trajectory_rows = decomp[(decomp["load_shape"] == HEADLINE_PROFILE) & (decomp["scenario"].isin(trajectories)) &
                          (decomp["start_year"] == HEADLINE_START) & (decomp["study_period_yrs_requested"] == HEADLINE_PERIOD)]

sel = pd.concat([profile_rows, trajectory_rows]).drop_duplicates(
    subset=["load_shape", "scenario", "start_year", "study_period_yrs_requested"])
assert (sel["fit_status"] == "full").all(), "not all selected rows are fit_status=='full'"

sel = sel.copy()
sel["temporal_kg"] = sel["kgco2_m2_b_mid"] - sel["kgco2_m2_a_mid"]
sel["spatial_kg"] = sel["kgco2_m2_c_mid"] - sel["kgco2_m2_b_mid"]
sel["trajectory_kg"] = sel["kgco2_m2_d_mid"] - sel["kgco2_m2_c_mid"]

# sort: headline row first, then the other two profiles, then the other four trajectories
sel["is_headline"] = (sel["load_shape"] == HEADLINE_PROFILE) & (sel["scenario"] == HEADLINE_TRAJECTORY)
sel["is_other_profile"] = (sel["load_shape"] != HEADLINE_PROFILE) & (sel["scenario"] == HEADLINE_TRAJECTORY)
sel = sel.sort_values(["is_headline", "is_other_profile"], ascending=[False, False])

out = pd.DataFrame({
    "Profile": sel["load_shape"],
    "Trajectory": sel["scenario"],
    "Start year": sel["start_year"],
    "Period (yr)": sel["study_period_yrs_requested"],
    "Fit status": sel["fit_status"],
    "Resolved value (kgCO2e/m2)": sel["kgco2_m2_a_mid"].round(1),
    "Static value (kgCO2e/m2)": sel["kgco2_m2_d_mid"].round(1),
    "Total error (kgCO2e/m2)": sel["total_error_kgco2_m2_mid"].round(1),
    "Total error (%)": sel["total_error_pct_of_Ea"].round(1),
    "Temporal component (kgCO2e/m2)": sel["temporal_kg"].round(1),
    "Spatial component (kgCO2e/m2)": sel["spatial_kg"].round(1),
    "Trajectory component (kgCO2e/m2)": sel["trajectory_kg"].round(1),
})

out.to_csv(TABLES / "table3_headline_decomposition.csv", index=False)
md_lines = ["| " + " | ".join(out.columns) + " |", "|" + "|".join(["---"] * len(out.columns)) + "|"]
for _, r in out.iterrows():
    md_lines.append("| " + " | ".join(str(v) for v in r.values) + " |")
(TABLES / "table3_headline_decomposition.md").write_text("\n".join(md_lines), encoding="utf-8")

print(f"Wrote table3_headline_decomposition.csv/.md ({len(out)} rows)")
print(out.to_string(index=False))
