"""
Category G2 uncertainty quantification (IPCC Approach 1 / analytic error propagation)
for the NI/SI generation-side monthly emission factor.

INPUT (read-only, no pipeline output touched):
    output/monthly_fuel_mix_NI_SI.csv
        columns: island, year, month, fuel_code, gen_mwh, co2_kg, share_pct,
                 weighted_ef_kg_per_MWh
    (this is the finest resolution at which a PER-FUEL generation split is
    published by this pipeline; the shipped hourly table
    output/hourly_emission_factor_NI_SI.csv carries only the already-blended
    total EF, with no per-fuel breakdown, so a genuinely per-fuel uncertainty
    propagation cannot honestly be built at hourly resolution from the
    currently shipped outputs -- see the accompanying report, Finding 4.)

METHOD -- IPCC Approach 1 (analytic/first-order error propagation), per
IPCC (2000) Good Practice Guidance and Uncertainty Management in National
Greenhouse Gas Inventories, Chapter 6, and IPCC (2006) 2019 Refinement Vol 1
Ch 3. Both PDFs are archived in ../validation_references/.

For each island-month, the blended EF is a generation-weighted sum of
per-fuel EFs:  EF = sum_i ( w_i * ef_i )  where w_i = gen_i / total_gen.
Treating each fuel's EF uncertainty as independent (a disclosed
simplification -- fuels are physically different combustion processes,
so this is more defensible than assuming correlation, but no country-level
correlation study exists to test it), first-order propagation gives:

    Var(EF) = sum_i ( w_i^2 * sigma_i^2 )

sigma_i is derived from IPCC 2006 Guidelines for National Greenhouse Gas
Inventories, Volume 2 (Energy), Chapter 2 (Stationary Combustion), Table 2.2
"Default emission factors for stationary combustion in the energy
industries" (kg CO2/TJ, net calorific basis) -- archived locally at
../validation_references/IPCC2006_Vol2_Ch2_StationaryCombustion.pdf, page 16.
That table gives a Default/Lower/Upper triplet per fuel; this script reads
off the Lower-Upper range AS PRINTED IN THE TABLE and uses
avg(|Default-Lower|, |Upper-Default|) / Default as a relative
1-sigma-equivalent half-width. This is a disclosed simplification: the
chapter's own text (Section 2.4.1) does not label the Table 2.2 range as a
literal 95% CI or literal 1-sigma -- it separately cites an IPCC 1996
default of ~7% overall CO2 EF uncertainty, and Table 2.13 (country-specific
studies) reports 95% CI ranges of +-0.5% to +-7% depending on fuel and
country. The Table-2.2-derived per-fuel figures used here (~2-4% for gas/
coal/diesel, ~16% for wood) sit inside that same 0.5-7% band for the
fossil fuels and are of a similar order to the wider biomass literature
range the chapter itself flags as less well measured -- so the method is
internally consistent with the chapter's own stated uncertainty ranges,
not an invented number.

Fuel coverage (disclosed, not forced):
  - CLG (coal)      -> Table 2.2 "Sub-Bituminous Coal"   96100 [92800-100000] kg/TJ
  - GAS (nat. gas)   -> Table 2.2 "Natural Gas"           56100 [54300-58300]  kg/TJ
  - DSL (diesel)     -> Table 2.2 "Gas/Diesel Oil"        74100 [72600-74800]  kg/TJ
  - WOOD (wood/waste)-> Table 2.2 "Wood/Wood Waste"      112000 [95000-132000] kg/TJ
  - HYD, WIN, SOL    -> zero combustion, EF and uncertainty both exactly zero.
  - GEO (geothermal) -> EXCLUDED from the quantified band. IPCC Vol 2 Ch 2
    covers FUEL COMBUSTION only; geothermal power-station CO2 originates
    from dissolved gas in the geothermal fluid, not fuel combustion, and is
    not covered by any table in this chapter. No IPCC-cited uncertainty
    range for it was found in this session's downloaded references. Rather
    than invent one, GEO's generation share is reported separately as
    "unquantified coverage" -- see the report's Finding 3 for why this
    matters and what a correct fix would need.
  - ELE              -> EXCLUDED, same reasoning; also negligible share
    (<0.2% in every island-month checked), so the effect on the reported
    coverage gap is immaterial regardless.
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "output" / "monthly_fuel_mix_NI_SI.csv"
OUT = Path(__file__).resolve().parent / "ipcc_uncertainty_by_island_month.csv"
OUT_ANNUAL = Path(__file__).resolve().parent / "ipcc_uncertainty_by_island_year.csv"

# IPCC 2006 GL Vol 2 Ch 2 Table 2.2 (kg CO2/TJ net calorific value), Energy Industries.
# (default, lower, upper) -- read directly off the downloaded PDF, page 16.
IPCC_TABLE_2_2 = {
    "CLG":  (96100.0, 92800.0, 100000.0),   # Sub-Bituminous Coal
    "GAS":  (56100.0, 54300.0, 58300.0),    # Natural Gas
    "DSL":  (74100.0, 72600.0, 74800.0),    # Gas/Diesel Oil
    "WOOD": (112000.0, 95000.0, 132000.0),  # Wood / Wood Waste
}
ZERO_EF_FUELS = {"HYD", "WIN", "SOL"}
EXCLUDED_FUELS = {"GEO", "ELE"}


def rel_half_width(default, lower, upper):
    """Relative 1-sigma-equivalent half-width, per the docstring above."""
    lo = abs(default - lower) / default
    hi = abs(upper - default) / default
    return (lo + hi) / 2.0


REL_SIGMA = {f: rel_half_width(*v) for f, v in IPCC_TABLE_2_2.items()}


def load_monthly_fuel_mix(path):
    rows = defaultdict(list)  # (island, year, month) -> [ {fuel_code, gen_mwh, ef} ]
    with open(path, newline="") as fh:
        r = csv.DictReader(fh)
        for row in r:
            key = (row["island"], int(row["year"]), int(row["month"]))
            gen = float(row["gen_mwh"])
            ef_raw = row["weighted_ef_kg_per_MWh"]
            # A blank EF occurs only when gen_mwh is exactly 0 (0/0, undefined) --
            # verified true for every blank row in this file before relying on it;
            # such a row contributes nothing to the weighted sums below regardless
            # of what ef is set to, since its weight (gen/total) is zero.
            if ef_raw == "":
                assert gen == 0.0, (
                    f"unexpected blank EF with nonzero gen: {row}"
                )
                ef = 0.0
            else:
                ef = float(ef_raw)
            rows[key].append(
                {
                    "fuel_code": row["fuel_code"],
                    "gen_mwh": gen,
                    "ef": ef,
                }
            )
    return rows


def propagate(fuels):
    """One island-month's list of per-fuel rows -> uncertainty summary dict."""
    total_gen = sum(f["gen_mwh"] for f in fuels)
    if total_gen <= 0:
        return None
    point_ef = sum(f["gen_mwh"] * f["ef"] for f in fuels) / total_gen

    var = 0.0
    quantified_gen = 0.0
    excluded_gen = 0.0
    dominant = []
    for f in fuels:
        code = f["fuel_code"]
        w = f["gen_mwh"] / total_gen
        if code in ZERO_EF_FUELS:
            quantified_gen += f["gen_mwh"]
            continue
        if code in EXCLUDED_FUELS:
            excluded_gen += f["gen_mwh"]
            continue
        if code not in REL_SIGMA:
            # Unrecognised fuel code not covered by this script's mapping --
            # do NOT silently assume zero uncertainty; treat as excluded/flagged.
            excluded_gen += f["gen_mwh"]
            continue
        sigma_i = f["ef"] * REL_SIGMA[code]
        contrib = (w * sigma_i) ** 2
        var += contrib
        quantified_gen += f["gen_mwh"]
        dominant.append((code, contrib))

    sigma_total = math.sqrt(var)
    ci95 = 1.96 * sigma_total
    dominant.sort(key=lambda x: -x[1])
    dominant_fuel = dominant[0][0] if dominant else None

    return {
        "point_ef_kg_per_mwh": point_ef,
        "sigma_kg_per_mwh": sigma_total,
        "ci95_lower_kg_per_mwh": point_ef - ci95,
        "ci95_upper_kg_per_mwh": point_ef + ci95,
        "ci95_pct_of_point": (ci95 / point_ef * 100.0) if point_ef > 0 else float("nan"),
        "quantified_coverage_pct": quantified_gen / total_gen * 100.0,
        "excluded_coverage_pct": excluded_gen / total_gen * 100.0,
        "dominant_uncertainty_fuel": dominant_fuel,
        "total_gen_mwh": total_gen,
    }


def main():
    data = load_monthly_fuel_mix(SRC)
    monthly_out = []
    for (island, year, month), fuels in sorted(data.items()):
        res = propagate(fuels)
        if res is None:
            continue
        res.update({"island": island, "year": year, "month": month})
        monthly_out.append(res)

    fieldnames = [
        "island", "year", "month", "point_ef_kg_per_mwh", "sigma_kg_per_mwh",
        "ci95_lower_kg_per_mwh", "ci95_upper_kg_per_mwh", "ci95_pct_of_point",
        "quantified_coverage_pct", "excluded_coverage_pct",
        "dominant_uncertainty_fuel", "total_gen_mwh",
    ]
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in monthly_out:
            w.writerow(row)

    # Annual, energy-weighted roll-up per island (re-propagate from monthly
    # variances treating months as independent -- another disclosed
    # simplification; same-year months share the same fleet, so this likely
    # UNDERSTATES correlation and therefore may understate the true annual
    # band slightly. Flagged, not hidden.)
    annual = defaultdict(list)
    for row in monthly_out:
        annual[(row["island"], row["year"])].append(row)

    annual_out = []
    for (island, year), rows in sorted(annual.items()):
        total_gen = sum(r["total_gen_mwh"] for r in rows)
        point_ef = sum(r["point_ef_kg_per_mwh"] * r["total_gen_mwh"] for r in rows) / total_gen
        var = sum((r["sigma_kg_per_mwh"] * r["total_gen_mwh"] / total_gen) ** 2 for r in rows)
        sigma = math.sqrt(var)
        ci95 = 1.96 * sigma
        cov = sum(r["quantified_coverage_pct"] * r["total_gen_mwh"] for r in rows) / total_gen
        annual_out.append(
            {
                "island": island,
                "year": year,
                "point_ef_kg_per_mwh": point_ef,
                "ci95_lower_kg_per_mwh": point_ef - ci95,
                "ci95_upper_kg_per_mwh": point_ef + ci95,
                "ci95_pct_of_point": (ci95 / point_ef * 100.0) if point_ef > 0 else float("nan"),
                "quantified_coverage_pct": cov,
                "total_gen_mwh": total_gen,
            }
        )

    with open(OUT_ANNUAL, "w", newline="") as fh:
        fieldnames2 = [
            "island", "year", "point_ef_kg_per_mwh", "ci95_lower_kg_per_mwh",
            "ci95_upper_kg_per_mwh", "ci95_pct_of_point", "quantified_coverage_pct",
            "total_gen_mwh",
        ]
        w = csv.DictWriter(fh, fieldnames=fieldnames2)
        w.writeheader()
        for row in annual_out:
            w.writerow(row)

    print(f"Wrote {len(monthly_out)} island-month rows -> {OUT}")
    print(f"Wrote {len(annual_out)} island-year rows -> {OUT_ANNUAL}")

    # Console summary
    ni = [r for r in annual_out if r["island"] == "NI"]
    si = [r for r in annual_out if r["island"] == "SI"]
    for label, rows in (("NI", ni), ("SI", si)):
        pct = [r["ci95_pct_of_point"] for r in rows if not math.isnan(r["ci95_pct_of_point"])]
        cov = [r["quantified_coverage_pct"] for r in rows]
        if pct:
            print(
                f"{label}: annual ci95_pct_of_point range "
                f"{min(pct):.2f}%-{max(pct):.2f}% across {len(rows)} years; "
                f"quantified generation coverage {min(cov):.1f}%-{max(cov):.1f}%"
            )


if __name__ == "__main__":
    main()
