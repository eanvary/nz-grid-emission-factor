"""Checks on the released tables in data/. Run: python -m pytest tests  (or python tests/test_released_data.py)"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "code" / "generation_pipeline"))
from fuel_attribution import periods_in_day  # noqa: E402

GEN = REPO / "data" / "historical" / "generation_basis"
CONS = REPO / "data" / "historical" / "consumption_basis"
hourly = pd.read_csv(GEN / "hourly_emission_factor_NI_SI.csv", parse_dates=["date"])


def test_one_row_per_clock_hour():
    rows = hourly.groupby(["island", "date"]).size()
    expected = np.where(periods_in_day(rows.index.get_level_values("date")) == 46, 23, 24)
    assert (rows.to_numpy() == expected).all()
    cons = pd.read_csv(CONS / "hourly_consumption_EF_NI_SI.csv", parse_dates=["date"])
    per_day = cons.groupby("date").size()
    assert (per_day.to_numpy() == np.where(periods_in_day(per_day.index) == 46, 23, 24)).all()


def test_no_empty_hours():
    assert not hourly["EF_kg_per_MWh"].isna().any()
    assert (hourly["total_gen_MWh"] > 0).all()


def test_hourly_daily_annual_totals_agree():
    daily = pd.read_csv(GEN / "daily_emission_factor_NI_SI.csv", parse_dates=["date"])
    annual = pd.read_csv(GEN / "annual_emission_factor_NI_SI.csv")
    cols = ["total_gen_MWh", "total_CO2_kg"]
    h2d = hourly.groupby(["island", "date"])[cols].sum().join(daily.set_index(["island", "date"])[cols], rsuffix="_d")
    for c in cols:
        assert np.allclose(h2d[c], h2d[f"{c}_d"], rtol=1e-9)
    h2a = hourly.assign(year=hourly.date.dt.year).groupby(["island", "year"])[cols].sum()
    h2a = h2a.join(annual.set_index(["island", "year"])[cols], rsuffix="_a")
    for c in cols:
        assert np.allclose(h2a[c], h2a[f"{c}_a"], rtol=1e-9)


def test_consumption_balances_generation():
    # Island consumption moves energy and CO2 between the islands; national totals must not change.
    for res, keys in [("daily", ["date"]), ("hourly", ["date", "hour"]), ("monthly", ["year", "month"]), ("annual", ["year"])]:
        gen = pd.read_csv(GEN / f"{res}_emission_factor_NI_SI.csv").groupby(keys)[["total_gen_MWh", "total_CO2_kg"]].sum()
        cons = pd.read_csv(CONS / f"{res}_consumption_EF_NI_SI.csv").set_index(keys)
        j = gen.join(cons, how="outer")
        assert len(j) == len(gen) == len(cons), res
        assert np.allclose(j.NI_consumption_MWh + j.SI_consumption_MWh, j.total_gen_MWh, rtol=1e-9), res
        assert np.allclose(j.NI_CO2_consumed_kg + j.SI_CO2_consumed_kg, j.total_CO2_kg, rtol=1e-9), res


def test_series_ends_in_december_2025():
    assert hourly["date"].max() == pd.Timestamp("2025-12-31")
    assert pd.read_csv(GEN / "annual_emission_factor_NI_SI.csv")["year"].max() == 2025


def test_decomposition_components_sum_to_total():
    d = pd.read_csv(REPO / "data" / "analysis_tables" / "phase3_decomposition_full.csv")
    parts = d.temporal_component + d.spatial_component + d.trajectory_component
    assert np.allclose(parts, d.total_error_d_minus_a, rtol=1e-9, atol=1e-9)


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
    print("all released-data checks pass")
