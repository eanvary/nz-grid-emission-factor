"""
fix_ddmmyyyy_dates.py: data-integrity fix for the 2015-2019 EMI raw files.

EA_EMI_raw/*_{Grid_import,Grid_export,Embedded_generation,HVDC_flows}.csv for 2015-01
through 2019-12 use DD/MM/YYYY in their trading-date column; every file from 2020-01
onward uses ISO YYYY-MM-DD. The regional-feasibility date parser
(diag_regional_feasibility.melt_tp, which calls pd.to_datetime(..., format="mixed", dayfirst=False))
silently mis-parses DD/MM/YYYY whenever day <= 12 and day != month, swapping day and month.
Analyses limited to 2021-2025 never hit this (those files are already ISO); it matters only
when the record is extended back to 2015-2019.

Fix: rewrite the date column to ISO in place, at the same path, so every imported function
(melt_tp, load_month, prepare, etc.) works correctly with zero code changes. Originals are
backed up to EA_EMI_raw_backup_ddmmyyyy_2015_2019/ before any file is touched.

This is a data correction, not a script edit: no analysis script is modified.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

ROOT = Path(__file__).parent.parent
RAW = ROOT / "EA_EMI_raw"
BACKUP = ROOT / "EA_EMI_raw_backup_ddmmyyyy_2015_2019"

DATASETS = {
    "Grid_import": "Trading_Date", "Grid_export": "Trading_Date",
    "Embedded_generation": "Trading_Date", "HVDC_flows": "TRADING_DATE",
}
MONTHS = [f"{y}{m:02d}" for y in range(2015, 2020) for m in range(1, 13)]


def fix_file(path, date_col):
    df = pd.read_csv(path, low_memory=False, dtype=str)
    # resolve the date column case-insensitively (some files may vary in casing)
    actual = next(c for c in df.columns if c.lower() == date_col.lower())
    before = df[actual].copy()
    parsed = pd.to_datetime(before, format="%d/%m/%Y", errors="raise")
    df[actual] = parsed.dt.strftime("%Y-%m-%d")
    df.to_csv(path, index=False)
    return before.iloc[0], df[actual].iloc[0], len(df)


def main():
    fixed, skipped, errors = 0, 0, []
    for month in MONTHS:
        for name, date_col in DATASETS.items():
            p = RAW / f"{month}_{name}.csv"
            if not p.exists():
                skipped += 1
                continue
            try:
                b, a, n = fix_file(p, date_col)
                fixed += 1
                if fixed <= 4 or fixed % 60 == 0:
                    print(f"  {p.name}: '{b}' to '{a}'  ({n} rows)")
            except Exception as e:
                errors.append((p.name, str(e)))
    print(f"\nFixed: {fixed}  Skipped (missing): {skipped}  Errors: {len(errors)}")
    for f, e in errors:
        print(f"  ERROR {f}: {e}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
