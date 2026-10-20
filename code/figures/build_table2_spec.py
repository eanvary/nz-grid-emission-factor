"""
Table 2: analysis specification table. One row per specification
dimension; every level list, count and cohort figure is read from the
tables at run time. No quantitative literal below is a result; the only
literals are word-count and column-order constants.
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"

decomp = pd.read_csv(TABLES / "phase3_decomposition_full.csv")
t1 = pd.read_csv(TABLES / "phase4_table1_full_decomposition.csv")
shapes = pd.read_csv(TABLES / "phase3_load_shapes_stylised.csv")
eui = pd.read_csv(TABLES / "phase3_eui_derived_v2.csv")
isl = pd.read_csv(TABLES / "phase3_annual_island_ef.csv")

rows = []

# 1. EF accounting basis. Generation is the headline ef_basis used to build
# E_a/E_b/E_c (matching phase3_annual_island_ef, which has no basis column
# and is the generation-side series). Consumption is the basis of the
# one-row sensitivity check.
ef_basis_levels = ["generation (headline)", "consumption (sensitivity)"]
rows.append(dict(
    Dimension="EF accounting basis", Levels=", ".join(ef_basis_levels),
    n=len(ef_basis_levels), Source_or_basis="phase3_consumption_sensitivity.py; ef_basis field",
    Note="Headline uses generation-side EF throughout"))

# 2. Island
islands = sorted(isl["island"].unique())
rows.append(dict(
    Dimension="Island", Levels=", ".join(islands) + " (building location: NI)",
    n=len(islands), Source_or_basis="phase3_annual_island_ef.csv",
    Note="Building located on NI; SI not modelled as a case"))

# 3. Scenario
scenarios = sorted(decomp["scenario"].unique())
rows.append(dict(
    Dimension="Scenario", Levels=", ".join(scenarios), n=len(scenarios),
    Source_or_basis="phase3_decomposition_full.csv", Note="MBIE EDGS scenario names, as published"))

# 4. Start year
start_years = sorted(decomp["start_year"].unique())
rows.append(dict(
    Dimension="Assessment start year", Levels=", ".join(str(y) for y in start_years),
    n=len(start_years), Source_or_basis="phase3_decomposition_full.csv", Note=""))

# 5. Demand profile
profiles = sorted(shapes["label"].unique())
rows.append(dict(
    Dimension="Demand profile", Levels=", ".join(profiles), n=len(profiles),
    Source_or_basis="phase3_load_shapes_stylised.csv", Note="Stylised hourly load shapes"))

# 6. Assessment period requested / retained
periods = sorted(decomp["study_period_yrs_requested"].unique())
ct = decomp.groupby(["start_year", "study_period_yrs_requested"])["fit_status"].first().reset_index()
n_cells = len(ct)
n_full_cells = int((ct["fit_status"] == "full").sum())
n_trunc_cells = n_cells - n_full_cells
rows.append(dict(
    Dimension="Assessment period requested", Levels=", ".join(str(p) for p in periods) + " years",
    n=len(periods), Source_or_basis="phase3_decomposition_full.csv", Note=""))
n_possible_cells = len(start_years) * len(periods)
rows.append(dict(
    Dimension="Assessment period retained (post-horizon rule)",
    Levels=f"{n_full_cells} full cells, {n_trunc_cells} truncated cells (2050-horizon rule)",
    n=n_cells, Source_or_basis="phase3_decomposition_full.csv, fit_status column",
    Note=f"{n_cells} of {n_possible_cells} start x period cells survive the horizon"))

# 7. EUI
headline_eui = eui[eui["cohort"].str.contains("Whole Building, NI, electricity-dominant") &
                    eui["cohort"].str.startswith("pre-2004")].iloc[0]
rows.append(dict(
    Dimension="Energy-use intensity", Levels=f"{headline_eui['eui_p10']:.0f}-{headline_eui['eui_p90']:.0f} "
    f"kWh/m2/yr (p10-p90), median {headline_eui['eui_median']:.0f}",
    n=int(headline_eui["n"]), Source_or_basis="phase3_eui_derived_v2.csv",
    Note="pre-2004, Whole Building, NI, electricity-dominant cohort"))

# 8. Decomposition order
order_levels = ["temporal-first (chosen)", "spatial-first (alternate)"]
rows.append(dict(
    Dimension="Decomposition order", Levels=", ".join(order_levels),
    n=len(order_levels), Source_or_basis="phase3_decomposition_full.csv; *_alt_component columns",
    Note="Trajectory collapsed last under both orders"))

# 9. Total result rows
n_full = int((decomp["fit_status"] == "full").sum())
n_trunc = int((decomp["fit_status"] != "full").sum())
rows.append(dict(
    Dimension="Total result rows", Levels=f"{n_full} full, {n_trunc} truncated",
    n=len(decomp), Source_or_basis="phase3_decomposition_full.csv", Note=""))

# Final row: instability flag count
n_unstable = int(t1["pct_breakdown_unstable"].sum())
rows.append(dict(
    Dimension="Non-interpretable pct-breakdown rows", Levels="flagged True/False",
    n=n_unstable, Source_or_basis="phase4_table1_full_decomposition.csv, pct_breakdown_unstable",
    Note="|total_error_pct_of_Ea| < 5, per the data"))

df = pd.DataFrame(rows).rename(columns={"Source_or_basis": "Source or basis"})
df = df[["Dimension", "Levels", "n", "Source or basis", "Note"]]

# word-count guard (<15 words per cell)
max_words = df.astype(str).map(lambda s: len(s.split())).max().max()
print(f"Max words in any Table 2 cell: {max_words} (must be < 15)")

df.to_csv(TABLES / "table2_analysis_specification.csv", index=False)
md_lines = ["| " + " | ".join(df.columns) + " |", "|" + "|".join(["---"] * len(df.columns)) + "|"]
for _, r in df.iterrows():
    md_lines.append("| " + " | ".join(str(v) for v in r.values) + " |")
(TABLES / "table2_analysis_specification.md").write_text("\n".join(md_lines), encoding="utf-8")
print(f"Wrote table2_analysis_specification.csv/.md ({len(df)} rows)")
print(df.to_string())
