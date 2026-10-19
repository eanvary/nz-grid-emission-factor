"""Energy use intensity cohort for Paper 3, with every North Island city in the NABERSNZ data (16 October 2026).
Same filters as analysis_paper/scripts/phase3_eui_derivation_v2.py (pre-2004 construction, Whole Building rating,
gas share <= 5%, rated area and electricity use > 0), but the island is assigned from a complete city list: the
earlier list left out Lower Hutt, Upper Hutt, Porirua and Paeroa. Writes the cohort table the analysis reads
(<copy_root>/analysis_paper/tables/phase3_eui_derived_v2.csv; the previous file is kept as *_before_all_cities.csv).
Usage: python p03_eui_all_ni_cities.py <copy_root>"""
import re, shutil, sys
from pathlib import Path
import numpy as np
import pandas as pd

SRC = Path(r"C:\Users\ehsan\OneDrive - AUT University\PhD\Database\Archetypes\NABERS\NABERS_With_Vintage_GCCI_v3.xlsx")
SI_CITIES = {"Christchurch", "Nelson", "Dunedin", "Ashburton", "Timaru", "Twizel"}
NI_CITIES = {"Auckland", "Wellington", "Hamilton", "Palmerston North", "Tauranga", "Whangarei", "Upper Hutt", "Lower Hutt",
             "Paraparaumu", "Rotorua", "New Plymouth", "Paeroa", "Whanganui", "Hastings", "Porirua", "Napier"}

df = pd.read_excel(SRC, sheet_name="NABERS + Vintage")
unknown = set(df["City"].dropna()) - SI_CITIES - NI_CITIES
assert not unknown, f"cities without an island: {unknown}"
df["total_energy_kwh"] = df["Electricity Use (kWh)"] + df["Gas Use (kWh)"]
df["gas_share_pct"] = np.where(df["total_energy_kwh"] > 0, 100 * df["Gas Use (kWh)"] / df["total_energy_kwh"], np.nan)
df["construction_year_parsed"] = df["Construction Year"].apply(lambda v: int(m.group()) if (m := re.search(r"(19|20)\d{2}", str(v))) else np.nan)
ed = df[(df["gas_share_pct"].fillna(0) <= 5) & (df["Rated Area"] > 0) & (df["Electricity Use (kWh)"] > 0) & df["City"].isin(NI_CITIES)].copy()
ed["eui_kwh_m2"] = ed["Electricity Use (kWh)"] / ed["Rated Area"]

def cohort(label, sub):
    return {"cohort": label, "n": len(sub), "eui_p10": sub.eui_kwh_m2.quantile(0.10), "eui_median": sub.eui_kwh_m2.median(), "eui_p90": sub.eui_kwh_m2.quantile(0.90)}
pre = ed[ed.construction_year_parsed < 2004]
rows = [cohort("pre-2004, Whole Building, NI, electricity-dominant", pre[pre["Type of Rating"] == "Whole Building"]),
        cohort("pre-2004, ALL rating types pooled (comparison only, NOT headline)", pre)]
for rt in ("Base Building", "Whole Building", "Tenancy"):
    rows.append(cohort(f"pre-2004, {rt} only", pre[pre["Type of Rating"] == rt]))
mod = ed[(ed.construction_year_parsed >= 2010) & (ed.construction_year_parsed < 2020) & (ed["Type of Rating"] == "Whole Building")]
rows.append(cohort("2010s (comparison), Whole Building, NI, electricity-dominant", mod))

head = pre[pre["Type of Rating"] == "Whole Building"]
bcols = [c for c in ("Building Name", "Address", "Building Address", "Premises") if c in head.columns]
n_bld = head[bcols[0]].nunique() if bcols else None
print(f"headline cohort: {len(head)} ratings of {n_bld} buildings (by {bcols[0] if bcols else 'n/a'}); median {head.eui_kwh_m2.median():.1f} kWh/m2")
print("cities in the headline cohort:", head["City"].value_counts().to_dict())

out = Path(sys.argv[1]).resolve() / "analysis_paper" / "tables" / "phase3_eui_derived_v2.csv"
bak = out.with_name("phase3_eui_derived_v2_before_all_cities.csv")
if not bak.exists(): shutil.copy(out, bak)
pd.DataFrame(rows).to_csv(out, index=False)
print("wrote", out)
