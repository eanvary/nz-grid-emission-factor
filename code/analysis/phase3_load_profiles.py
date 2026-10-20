"""
Phase 3 input: three stylised commercial load shapes (not metered or
BEES-derived, because no such data was available to the project).
Each is a weight over (day-of-week type, hour-of-day) and is
month-independent: no seasonality is assumed for the building load itself,
and only the grid EF varies seasonally. Each shape is normalised to sum to
1.0 over a standard non-leap 8760-hour year. Each therefore represents the
same fixed annual energy total distributed differently across hours, which
makes decomposition results comparable across shapes.
"""
import numpy as np
import pandas as pd
from pathlib import Path

TABLES = Path(__file__).resolve().parents[1] / "tables"
TABLES.mkdir(parents=True, exist_ok=True)


def build_shape(hourly_weekday, hourly_weekend, label):
    """hourly_weekday/weekend: 24 raw relative-intensity values (0-23h), not yet
    normalised to any specific calendar year. A year is not an exact number of
    weeks, so exact normalisation is deferred to application time (see
    `apply_shape_to_year` in phase3_decomposition.py). Returns [dow, hour,
    raw_intensity, label]. The shape assumes a stationary weekly pattern with no
    seasonal or day-to-day variation. This is a stated simplification of a
    stylised profile, not a claim about real building behaviour."""
    wd = np.array(hourly_weekday, dtype=float)
    we = np.array(hourly_weekend, dtype=float)
    rows = []
    for dow in range(7):  # 0=Mon .. 6=Sun
        vals = we if dow >= 5 else wd
        for h in range(24):
            rows.append({"dow": dow, "hour": h, "raw_intensity": vals[h]})
    df = pd.DataFrame(rows)
    df["label"] = label
    return df


# Shape 1: daytime office (weekday 08:00-18:00 occupied, small nighttime
# base load for servers/security; weekends near-zero)
office_wd = [0.2]*7 + [0.6,1.0,1.0,1.0,1.0,0.8,1.0,1.0,1.0,1.0,0.6] + [0.3]*6
# hours 0-6 (7 vals)=0.2, 7-17 (11 vals) occupied profile, 18-23 (6 vals)=0.3; length fixed at 24
office_wd = [0.2]*7 + [0.5,0.9,1.0,1.0,1.0,0.85,1.0,1.0,1.0,0.9,0.5] + [0.3]*6
assert len(office_wd) == 24, len(office_wd)
office_we = [0.15]*24  # skeleton weekend base load only
shape_office = build_shape(office_wd, office_we, "daytime_office")

# Shape 2: 24/7 continuous operation (e.g. data centre / cold storage /
# continuous process): flat, no weekday/weekend or diurnal variation
flat = [1.0]*24
shape_247 = build_shape(flat, flat, "continuous_24_7")

# Shape 3: evening-weighted (e.g. residential-pattern-adjacent retail /
# hospitality; peak in the evening, moderate midday, low overnight, present on
# weekends too, unlike the office shape)
evening_wd = [0.25]*7 + [0.4,0.5,0.5,0.5,0.5,0.6,0.6,0.6,0.7,0.9,1.0] + [1.0,0.9,0.7,0.5,0.4,0.3]
# ensure 24 values: 7 (night) + 11 (day ramp) + 6 (evening decay) = 24
assert len(evening_wd) == 24, len(evening_wd)
evening_we = [0.3]*7 + [0.6,0.7,0.8,0.8,0.9,0.9,1.0,1.0,1.0,1.0,1.0] + [0.9,0.8,0.7,0.6,0.5,0.4]
assert len(evening_we) == 24, len(evening_we)
shape_evening = build_shape(evening_wd, evening_we, "evening_weighted")

all_shapes = pd.concat([shape_office, shape_247, shape_evening], ignore_index=True)
all_shapes.to_csv(TABLES / "phase3_load_shapes_stylised.csv", index=False)

print("Wrote phase3_load_shapes_stylised.csv (raw, dow x hour intensities; "
      "3 shapes: daytime_office, continuous_24_7, evening_weighted)")
print(all_shapes.groupby("label")["raw_intensity"].agg(["min", "max", "mean"]))
