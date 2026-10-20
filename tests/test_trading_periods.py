"""Checks for the trading-period to clock-hour mapping in code/generation_pipeline/fuel_attribution.py.
Run: python -m pytest tests  (or python tests/test_trading_periods.py)"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code" / "generation_pipeline"))
from fuel_attribution import periods_in_day, shape_hours, tp_hours, tp_to_hours  # noqa: E402


def test_day_lengths_follow_nz_daylight_saving():
    assert list(periods_in_day(["2024-09-29", "2025-04-06", "2025-06-01"])) == [46, 50, 48]


def test_hours_skip_and_repeat_0200():
    assert list(tp_hours(48)[[0, 1, 2, 47]]) == [0, 0, 1, 23]
    assert 2 not in tp_hours(46) and list(tp_hours(46)[[3, 4, 45]]) == [1, 3, 23]
    assert list(tp_hours(50)[[3, 4, 7, 8, 49]]) == [1, 2, 2, 3, 23]


def test_energy_kept_and_missing_hour_marked():
    tp = np.zeros((3, 50))
    tp[0, :48] = tp[1, :46] = tp[2, :50] = 1.0
    h = tp_to_hours(tp, np.array([48, 46, 50]))
    assert (h[0] == 2).all()
    assert np.isnan(h[1, 2]) and np.nansum(h[1]) == 46
    assert h[2, 2] == 4 and h[2].sum() == 50


def test_shape_has_one_value_per_hour_on_every_day():
    days = ["2025-06-01", "2024-09-29", "2025-04-06"]  # normal, clocks forward, clocks back
    n = periods_in_day(days)
    tp = np.zeros((3, 50))
    for row, k in enumerate(n):
        tp[row, :k] = 1.0
    s = shape_hours(tp_to_hours(tp, n), n)
    assert s.shape == (3, 24) and not np.isnan(s).any()
    assert (s == 2).all()  # no gap at 02:00 and no doubled 02:00


def test_data_beyond_the_day_length_is_rejected():
    try:
        tp_to_hours(np.ones((1, 50)), np.array([48]))
    except ValueError:
        return
    raise AssertionError("expected ValueError")


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
    print("all trading-period checks pass")
