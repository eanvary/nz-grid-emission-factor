"""
BDG2 real-data sensitivity test, step 1: extract a small, diverse sample of
real hourly office-building electricity meters from the Building Data Genome
Project 2 (Miller et al. 2020, Sci Data 7:368), for use as a REAL (not
stylised) building load shape in a sensitivity re-run of the Phase 3
decomposition. NZ building data is not accessible; BDG2 is Northern-
Hemisphere (US/UK/Ireland) and is used here explicitly as an out-of-region
proxy to test whether real (vs. stylised) hourly demand timing changes the
error decomposition -- not as a claim about NZ building behaviour.

Kept entirely separate from analysis_paper/{scripts,tables,figures,logs} --
this whole exercise lives under analysis_paper/sensitivity_realdata_bdg2/.
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # .../sensitivity_realdata_bdg2
RAW = ROOT / "raw" / "repo" / "data"
TABLES = ROOT / "tables"
TABLES.mkdir(parents=True, exist_ok=True)

# 6 real office buildings, chosen for climate/site diversity across BDG2's
# available sites (all Northern Hemisphere -- see hemisphere-shift note in
# step 2). Sizes chosen in the 5,000-15,000 sqm range to stay broadly
# comparable to the NZ NABERS office cohort used in the main assessment.
BUILDINGS = [
    "Bull_office_Chantel",   # US/Central,  9,655 sqm
    "Eagle_office_Tia",      # US/Eastern,  11,404 sqm
    "Fox_office_Demetrius",  # US/Mountain, 14,463 sqm
    "Hog_office_Josefina",   # US/Central,  14,636 sqm
    "Lamb_office_Bertha",    # Europe/London, 5,336 sqm
    "Wolf_office_Cary",      # Europe/Dublin, 11,795 sqm
]

meta = pd.read_csv(RAW / "metadata" / "metadata.csv")
sample_meta = meta[meta["building_id"].isin(BUILDINGS)][
    ["building_id", "site_id", "sqm", "sqft", "timezone", "primaryspaceusage", "yearbuilt"]]
print("Selected buildings:")
print(sample_meta.to_string(index=False))
sample_meta.to_csv(TABLES / "sample_buildings_metadata.csv", index=False)

print("\nReading electricity_cleaned.csv, columns=[timestamp] + 6 buildings only (usecols)...")
elec = pd.read_csv(RAW / "meters" / "cleaned" / "electricity_cleaned.csv",
                    usecols=["timestamp"] + BUILDINGS, parse_dates=["timestamp"])
print(f"Shape: {elec.shape}")
print(f"Date range: {elec['timestamp'].min()} to {elec['timestamp'].max()}")
print(f"\nMissing-value counts:\n{elec[BUILDINGS].isna().sum()}")
print(f"\nCompleteness (%% non-null):\n{(100 * elec[BUILDINGS].notna().mean()).round(1)}")

elec.to_csv(TABLES / "sample_buildings_hourly_electricity_kwh.csv", index=False)
print(f"\nWrote sample_buildings_hourly_electricity_kwh.csv ({len(elec)} rows)")

print("\nBasic stats (kWh, presumably; BDG2 cleaned data is in kWh per README/wiki):")
print(elec[BUILDINGS].describe().to_string())
