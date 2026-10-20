# Consistent-scope projection variant

The variant is built by `code/projection_pipeline/build_edgs_consistent_scope.py`. Its docstring gives the
definitions.

## Boundary break in MBIE's accounting at 2023/2024

- MBIE's historical electricity emissions (EDGS 2024 Results, Status Historical, to 2023) include the whole
  geothermal fleet. For 2015 they give 4.872 Mt, against 4.874 Mt with geothermal (4.061 Mt without) in the
  MBIE quarterly workbook.
- MBIE's projected totals for 2024 to 2030 equal combustion from MBIE's own fuel input, to within +0.00 to
  +0.04 Mt, once MBIE's implied gas factor (about 51.95 kg/GJ) is used. That leaves no room for the existing
  geothermal fleet's emissions of about 0.48 Mt.
- MBIE's geothermal heat input steps from 198.8 PJ (2023, historical) to 263.5 PJ (2024, projected) while
  generation stays nearly constant (EDGS 2024 Results, 'Electricity generation use', Geothermal).
- The consistent-scope variant therefore does not reproduce MBIE's published totals, by construction. Check 2
  is reported unforced for both variants (`check2_by_variant.csv`).

## Grid-injection denominator (`EF_*_grid`)

grid GWh = MBIE emissions / MBIE grid emission factor × k, with k = 0.9741. The factor k is the 2015–2023 mean
of metered generation divided by implied MBIE grid generation, Reference scenario. By year it is 2015 0.9780,
2016 0.9753, 2017 0.9755, 2018 0.9700, 2019 0.9707, 2020 0.9805, 2021 0.9784, 2022 0.9709 and 2023 0.9678.

The same grid share is applied to each island, which is an estimate. `EF_NI` and `EF_National` keep the
total-generation denominator.

## Assumption: Glenbrook-class coal

7.63 PJ of coal a year carries zero emissions in every scenario and year. MBIE's data isolate it only in the
Environmental and Innovation scenarios from 2032. Before 2032 it is assumed to sit inside the 13.59 PJ in all
scenarios.
