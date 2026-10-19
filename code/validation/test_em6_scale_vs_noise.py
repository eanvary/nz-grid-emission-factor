"""
Is a fuel's em6 gap noise, or a systematic scale offset?

WHY THIS EXISTS (2026-09-23)
The em6 cross-check reports solar at correlation 0.97 but a mean absolute daily
difference of 39%. That pairing was read as noise: solar's daily totals are small,
so small absolute differences become large percentages.

High correlation beside a large percentage gap is also the signature of a scale
mismatch, so it is worth separating the two before believing either. The test is
the ratio em6 / ours, day by day:

  noise on small numbers   ratio scatters about 1.0, with a large spread
  scale or coverage offset ratio sits away from 1.0, with a small spread

The same diagnostic doubles as a unit check. A units error would move every fuel
by the same factor, so fuels landing at a ratio near 1.0 rule that out.

It also re-derives this project's own side straight from the raw EMI files, so a
bug in the cross-check aggregation would show up as a ratio away from 1.0 in the
"ours rebuilt / ours as shipped" column.

Run: python test_em6_scale_vs_noise.py
"""
import glob
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TP = [f"TP{i}" for i in range(1, 49)]
FUEL_PREFIX = {"SOL": ("sol", "pv"), "WIN": ("win", "onw"), "HYD": ("hyd",),
               "GEO": ("geo",), "GAS": ("gas",), "CLG": ("coal", "clg", "cg")}

ov = pd.read_csv(os.path.join(HERE, "em6_crosscheck_overlap.csv"))
ov["date"] = pd.to_datetime(ov.trading_date).dt.date

# Rebuild this project's side from the raw EMI files, independently
years = sorted({str(d)[:4] for d in ov.date})
files = [f for f in sorted(glob.glob(os.path.join(ROOT, "EA_EMI_raw",
                                                  "*_Generation_MD.csv")))
         if any(os.path.basename(f).startswith(y) for y in years)]
parts = []
for f in files:
    d = pd.read_csv(f, low_memory=False)
    dc = [c for c in d.columns if c.lower() == "trading_date"][0]
    have = [c for c in TP if c in d.columns]
    d["mwh"] = d[have].apply(pd.to_numeric, errors="coerce").sum(axis=1) / 1000.0
    d["date"] = pd.to_datetime(d[dc]).dt.date
    d["fl"] = d.Fuel_Code.astype(str).str.lower()
    parts.append(d[["date", "fl", "mwh"]])
raw = pd.concat(parts, ignore_index=True)

print(f"{'fuel':<6}{'n':>5}{'ours':>10}{'em6':>10}{'ratio':>8}{'spread':>9}"
      f"{'verdict':>34}{'rebuild':>9}")
print("-" * 92)
rows = []
for fuel in ["HYD", "GEO", "WIN", "SOL", "GAS", "CLG"]:
    s = ov[(ov.fuel_std == fuel) & (ov.gen_mwh > 0) & (ov.gen_mwh_em6 > 0)]
    if len(s) < 5:
        continue
    r = s.gen_mwh_em6 / s.gen_mwh
    ratio, cv = r.mean(), r.std() / r.mean()

    mine = raw[raw.fl.str.startswith(FUEL_PREFIX[fuel])].groupby("date").mwh.sum()
    chk = s.set_index("date").gen_mwh
    both = pd.concat([mine.rename("rebuilt"), chk.rename("shipped")], axis=1).dropna()
    rebuild = (both.rebuilt / both.shipped).mean() if len(both) else float("nan")

    if abs(ratio - 1) < 0.10 and cv < 0.10:
        v = "agrees"
    elif cv < 0.20:
        v = f"systematic offset, x{ratio:.2f}"
    else:
        v = "noisy, no single explanation"
    print(f"{fuel:<6}{len(s):>5}{s.gen_mwh.mean():>10.1f}{s.gen_mwh_em6.mean():>10.1f}"
          f"{ratio:>8.3f}{cv * 100:>8.1f}%{v:>34}{rebuild:>9.3f}")
    rows.append({"fuel": fuel, "n_days": len(s),
                 "ours_mean_mwh_day": round(s.gen_mwh.mean(), 1),
                 "em6_mean_mwh_day": round(s.gen_mwh_em6.mean(), 1),
                 "mean_ratio_em6_over_ours": round(ratio, 3),
                 "cv_of_ratio_pct": round(cv * 100, 1),
                 "verdict": v,
                 "ours_rebuilt_over_shipped": round(rebuild, 3)})

out = os.path.join(HERE, "em6_scale_vs_noise.csv")
pd.DataFrame(rows).to_csv(out, index=False)
print(f"\nwritten: {os.path.basename(out)}")
print("\nReading it: 'spread' is the coefficient of variation of the daily ratio.")
print("A small spread away from 1.0 is a coverage or scale difference, not noise.")
print("'rebuild' recomputes this project's side from the raw EMI files; 1.000")
print("means the shipped cross-check aggregation reproduces exactly.")
