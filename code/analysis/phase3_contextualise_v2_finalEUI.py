"""
Phase 3: absolute (kgCO2e/m2) decomposition figures, using the EUI of the
pre-2004, Whole Building, NI, electricity-dominant NABERS cohort (n=132;
phase3_eui_derived_v2.csv).

Kept as a re-runnable script so the calculation is reproducible. The
figures use this derived EUI, not an illustrative one.
"""
import pandas as pd
from pathlib import Path

TABLES = Path(__file__).resolve().parents[1] / "tables"

eui = pd.read_csv(TABLES / "phase3_eui_derived_v2.csv")
headline_row = eui[eui["cohort"] == "pre-2004, Whole Building, NI, electricity-dominant"].iloc[0]
EUI_LOW, EUI_MID, EUI_HIGH = headline_row["eui_p10"], headline_row["eui_median"], headline_row["eui_p90"]
print(f"Using EUI from phase3_eui_derived_v2.csv: p10={EUI_LOW:.1f}, median={EUI_MID:.1f}, p90={EUI_HIGH:.1f} kWh/m2/yr")

decomp = pd.read_csv(TABLES / "phase3_decomposition_full.csv")
for col_src, col_out in [("E_a_hourly_island", "a"), ("E_b_annual_island", "b"),
                          ("E_c_annual_national", "c"), ("E_d_static_base", "d")]:
    decomp[f"kgco2_m2_{col_out}_mid"] = decomp[col_src] * EUI_MID
decomp["total_error_kgco2_m2_mid"] = decomp["total_error_d_minus_a"] * EUI_MID
decomp["annualised_a_mid"] = decomp["kgco2_m2_a_mid"] / decomp["n_years_used"]
decomp["annualised_d_mid"] = decomp["kgco2_m2_d_mid"] / decomp["n_years_used"]
decomp["pct_breakdown_unstable"] = decomp["total_error_pct_of_Ea"].abs() < 5

out_path = TABLES / "phase3_decomposition_contextualised_v3_finalEUI.csv"
decomp.to_csv(out_path, index=False)
print(f"Wrote {out_path} ({len(decomp)} rows)")

hl = decomp[(decomp["scenario"] == "Reference") & (decomp["start_year"] == 2027) &
            (decomp["load_shape"] == "daytime_office")]
print("\nHeadline (Reference, NI, daytime_office, start=2027):")
print(hl[["study_period_yrs_requested", "fit_status", "n_years_used",
          "kgco2_m2_a_mid", "kgco2_m2_d_mid", "total_error_kgco2_m2_mid",
          "annualised_a_mid", "annualised_d_mid"]].to_string(index=False))
