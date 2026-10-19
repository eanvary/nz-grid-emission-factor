"""
VALIDATION UPDATE (follow-up brief C): the Step 5 HVDC capacity violation (103/135
scenario-years, up to 2,662 MW vs the cited 1,200 MW) was tested against three candidate
pipeline artifacts (DSR island split, pre-2024 solar shape, uniform loss-ratio) via genuine
re-runs in build_edgs_hvdc_sensitivity.py, plus checked against MBIE's own report text and a
per-scenario demand-growth correlation. VERDICT: GENUINE FINDING, not a pipeline artifact.
Even after correcting the two real simplifications found (DSR 48/52 split + real 2024 solar
shape), 97/135 scenario-years (72%) still exceed the cited capacity, max transfer 2,391 MW
(vs the original 2,662 MW - both figures reported, not one replacing the other). The
loss-ratio bounding test moved violations UP in both directions tested (+10% NI or +10% SI),
not down - the uniform-loss simplification is not inflating the finding. Violation magnitude
correlates 0.78-0.96 with national peak demand growth in EVERY scenario individually. MBIE's
own EDGS report does not mention Cook Strait HVDC or inter-island transmission capacity by
name, but does state EDGS scenarios directly feed Transpower's transmission-investment
approval process (Capex IM) - relevant institutional context, not independent corroboration
of this specific number. Full detail: README_EDGS_hourly.md, edgs_hvdc_sensitivity_summary.csv.

Module 7 (follow-up brief B): island-resolved consumption-side emission factor.

Adds ef_basis='consumption', island='NI'/'SI' rows to edgs_hourly_emission_factor.parquet,
alongside the existing 'National' consumption row (kept unchanged, additive only).

METHOD (Steps 1-2, per brief, with one documented fix):
  Step 1 - island DEMAND(t): MBIE national annual demand x MBIE Island share of demand
           (NI share; SI = 1-NI share) x each island's OWN historical hourly shape
           (edgs_shape_demand.parquet, Module 4/Assumption 1). Used ONLY as the EF
           denominator (Step 6) - no new assumption beyond the already-declared Assumption 1.
  Step 2 - island GENERATION-LEVEL LOAD(t): the brief's literal formula
           (island_demand(t) x national_grossup_factor) was tested and found to produce a
           genuine, non-trivial national hourly imbalance (std ~383 MWh, max ~1713 MWh =~
           27.6% of mean hourly demand for a sample scenario-year) - NOT rounding-error
           level. Cause: Module 5's thermal dispatch sets each fuel's ANNUAL total to MBIE's
           published figure while only the SHAPE (not the absolute level) follows the
           demand-minus-renewables residual; since 100% of thermal capacity is NI (Module 2),
           this manifests entirely as a NI-side gap between "demand-shape-scaled load" and
           "actually dispatched generation" at the national level.
           FIX (documented, minimal): island generation-level load is renormalised so the
           NATIONAL total exactly equals ACTUAL national generation(t) (already computed,
           already reconciled) at every hour, while the ISLAND SPLIT still uses only MBIE's
           demand share and Assumption 1's per-island shape (the grossup factor cancels out
           of the split ratio - it was a uniform national scalar). This guarantees Step 3's
           symmetry check passes at floating-point precision by construction, and does not
           touch build_edgs_dispatch.py's own generation/combustion calculation.
  Step 3 - required_transfer_to_ISLAND(t) = island_genload(t) - island_generation(t).
           Sign convention: POSITIVE = net import requirement; NEGATIVE = net export surplus.
  Step 4 - historical validation (2021-2025): see the printed/logged discussion. FINDING:
           no independently-metered per-island DEMAND dataset exists in this project (checked:
           EA_EMI_raw / EA data folders contain only generation-side + plant + NSP data).
           The historical Consumption pipeline's own "consumption" figures are DEFINED as
           generation + real metered HVDC transfer (Consumption_Island/build_consumption_ef_*.py:
           "Consumption_NI(t) = Generation_NI(t) + net_to_NI(t)"), so testing
           demand-minus-generation against net_to_NI_MWh using that data is TAUTOLOGICAL
           (confirmed: max abs diff ~5e-13, correlation exactly 1.0) - not independent
           evidence. Reported honestly rather than presented as validation. The one
           genuinely independent check available: real HVDC direction (SI net-exports to NI
           in 77% of hours) matches NZ's well-documented SI hydro surplus - a plausibility
           check only, not a precision validation.
  Step 5 - HVDC capacity: Transpower, "HVDC link upgrade programme" (accessed 2026-07),
           current rated transfer capacity 1200 MW (cable-limited). An upgrade to 1400 MW
           (a fourth submarine cable) received Commerce Commission approval 18 June 2026
           ($1.1bn Cook Strait cable investment, Stage 1) - cable replacement/installation
           expected to complete in the early 2030s (verified, Brief D: both Transpower's own page and
           the Commerce Commission's approval decision cite this figure independently).
           1200 MW is used throughout 2024-2050 as the currently-operational figure
           (conservative; does not assume the upgrade's in-service date, which postdates
           several scenario-years' first violations reported below).
  Step 6 - emissions attributed by EXPORTING island's generation-side EF (physically
           correct: emissions occur where generation happens). National reconciliation
           (CO2_consumed_NI + CO2_consumed_SI == national combustion CO2) is a MANDATORY
           check, not a rounding note.

KNOWN LIMITATION (carried over, not fixed here): Assumption 2's DSR/battery is booked
100% to NI in the existing generation table even though GEM build schedule capacity is
~48%/52% NI/SI. This is the separately-flagged "battery/BESS capacity gap" priority (see
README), not addressed in this module; island generation_NI(t) therefore already includes
this known simplification via the existing edgs_hourly_generation.parquet.
"""
import numpy as np
import pandas as pd

from edgs_common import ASSUMPTIONS_XLSX, OUT_DIR, SCENARIOS, YEARS, ROOT, log_factory

log, lines = log_factory()

HVDC_CAPACITY_MW = 1200.0
HVDC_SOURCE = ("Transpower, \"HVDC link upgrade programme\" (transpower.co.nz/hvdc-upgrade, "
              "accessed 2026-07): current rated transfer capacity 1200 MW (cable-limited); "
              "1400 MW upgrade (4th cable) approved by the Commerce Commission 18 June 2026 "
              "($1.1bn Stage 1 investment; both Transpower's own page and the Commerce "
              "Commission decision independently cite the 1400 MW figure), expected complete "
              "the early 2030s - not assumed here (1200 MW used throughout 2024-2050).")

# Load prerequisites
targets = pd.read_parquet(OUT_DIR / "edgs_annual_targets.parquet")
dem_shape = pd.read_parquet(OUT_DIR / "edgs_shape_demand.parquet")
dem_shape = dem_shape[dem_shape["template_year"] == 2021]  # matches dispatch.py's CENTRAL_TEMPLATE
gen = pd.read_parquet(OUT_DIR / "edgs_hourly_generation.parquet")
ef = pd.read_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet")

isd = pd.read_excel(ASSUMPTIONS_XLSX, sheet_name="Island share of demand")
isd = isd[isd["Variable"] == "North Island share of national demand"]
ni_share_map = isd.set_index(["Scenario", "TimePeriod"])["Value"].to_dict()


def year_calendar(year):
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return pd.DataFrame({"datetime_hour": idx, "month": idx.month, "day": idx.day, "hour": idx.hour})


def map_weights(cal, wtab, template_year=2021):
    """Weekday-aligned template mapping (Brief W, 2026-09-16) -- identical logic to
    build_edgs_dispatch.map_weights so the consumption denominator uses the same template
    day as the dispatch demand series. Each projected day takes the template day with the
    same weekday nearest to the same calendar date (shift <= 3 days)."""
    import os as _os
    if _os.environ.get("EDGS_DISABLE_WEEKDAY_ALIGN", "0") == "1":
        m = cal.merge(wtab, on=["month", "day", "hour"], how="left")
        w = m["weight"].fillna(0.0).to_numpy()
        s = w.sum()
        return w / s if s > 0 else w
    tmpl = wtab.copy()
    tmpl["tdate"] = pd.to_datetime({"year": template_year, "month": tmpl["month"], "day": tmpl["day"]}, errors="coerce")
    tmpl = tmpl.dropna(subset=["tdate"])
    lut = {(d, h): wgt for d, h, wgt in zip(tmpl["tdate"].dt.normalize(), tmpl["hour"], tmpl["weight"])}
    tdays = set(tmpl["tdate"].dt.normalize().unique())
    out = np.zeros(len(cal))
    days = pd.to_datetime(cal["datetime_hour"]).dt.normalize()
    hours = cal["hour"].to_numpy()
    cache = {}
    for i, (d, h) in enumerate(zip(days, hours)):
        if d not in cache:
            try:
                base = pd.Timestamp(year=template_year, month=d.month, day=d.day)
            except ValueError:
                base = pd.Timestamp(year=template_year, month=d.month, day=28)
            shift = (d.weekday() - base.weekday() + 3) % 7 - 3
            cand = base + pd.Timedelta(days=int(shift))
            if cand not in tdays:
                cand = base + pd.Timedelta(days=int(shift - 7 if shift > 0 else shift + 7))
            if cand not in tdays:
                cand = base
            cache[d] = cand
        out[i] = lut.get((cache[d], h), 0.0)
    s = out.sum()
    return out / s if s > 0 else out


w_ni_base = dem_shape[dem_shape.island == "NI"][["month", "day", "hour", "weight"]]
w_si_base = dem_shape[dem_shape.island == "SI"][["month", "day", "hour", "weight"]]

# Historical validation (run once, before trusting the forward method)
log("=== Step 4: historical validation (2021-2025) ===")
cons = pd.read_csv(ROOT / "Consumption_Island" / "output" / "hourly_consumption_EF_NI_SI.csv")
implied_transfer_NI = cons["NI_consumption_MWh"] - (cons["NI_consumption_MWh"] - cons["net_to_NI_MWh"])
max_diff = (implied_transfer_NI - cons["net_to_NI_MWh"]).abs().max()
corr = np.corrcoef(implied_transfer_NI, cons["net_to_NI_MWh"])[0, 1]
log(f"  Literal test (historical 'demand' minus 'generation' vs net_to_NI_MWh): "
    f"max abs diff = {max_diff:.2e} MWh, correlation = {corr:.6f}")
log("  FINDING: this is a TAUTOLOGY, not independent validation. The historical Consumption "
    "pipeline DEFINES 'consumption' as generation + real metered HVDC transfer "
    "(Consumption_NI(t) = Generation_NI(t) + net_to_NI(t)), so 'demand minus generation' "
    "reproduces net_to_NI_MWh by construction (confirmed: diff at floating-point precision). "
    "No independently-metered per-island DEMAND dataset exists in this project's local data "
    "(checked EA_EMI_raw and EA data: generation, plant, and NSP files only) to run a true "
    "independent test.")
si_export_share = (cons["net_to_NI_MWh"] > 0).mean() * 100
log(f"  Best available independent check: real HVDC direction — SI net-exports to NI in "
    f"{si_export_share:.1f}% of historical hours, consistent with NZ's well-documented SI "
    f"hydro generation surplus. This is a plausibility check only, not a precision validation.")
HIST_VALIDATION_NOTE = (
    f"Step 4 (historical validation): literal demand-minus-generation test vs real net_to_NI_MWh "
    f"is TAUTOLOGICAL (no independent island demand data exists locally; correlation=1.0 by "
    f"construction, not evidence). Independent plausibility check: real SI->NI export direction "
    f"in {si_export_share:.0f}% of hours matches known SI hydro surplus.")

# Steps 1-3, 5-6: per scenario-year hourly island consumption
gen["year"] = pd.to_datetime(gen["datetime_hour"]).dt.year
ef["year"] = pd.to_datetime(ef["datetime_hour"]).dt.year

cons_rows = []
symmetry_report = []
capacity_flags = []
reconcile_report = []

for scenario in SCENARIOS:
    for year in YEARS:
        cal = year_calendar(year)
        H = len(cal)
        dt = cal["datetime_hour"].to_numpy()
        t = targets[(targets.scenario == scenario) & (targets.year == year)]
        demand_twh = float(t[t.metric == "annual_demand"]["value"].iloc[0])
        ni_share = float(ni_share_map.get((scenario, year), 0.61))
        demand_mwh = demand_twh * 1e6

        w_ni = map_weights(cal, w_ni_base)
        w_si = map_weights(cal, w_si_base)

        # Island demand (EF denominator only)
        island_demand_NI = demand_mwh * ni_share * w_ni
        island_demand_SI = demand_mwh * (1 - ni_share) * w_si

        # Actual per-island generation (existing, unmodified)
        g = gen[(gen.scenario == scenario) & (gen.year == year)]
        g_NI = g[g.island == "NI"].groupby("datetime_hour")["generation_mwh"].sum().reindex(dt, fill_value=0.0).to_numpy()
        g_SI = g[g.island == "SI"].groupby("datetime_hour")["generation_mwh"].sum().reindex(dt, fill_value=0.0).to_numpy()
        nat_gen = g_NI + g_SI

        # Island generation-level load, renormalised to actual nat_gen(t)
        # One hour/year has zero valid demand-shape weight (the DST spring-forward transition
        # hour, last Sunday of September, NZ clocks skip 23:00-23:59 - the SAME documented
        # artifact as the historical pipeline's hourly EF table). At that hour only, fall back
        # to MBIE's annual island share alone (no shape weighting) so the split still sums to
        # 1 exactly and the Step 3 symmetry check holds at true floating-point precision
        # everywhere, not just at 8759/8760 hours.
        raw_share_NI = ni_share * w_ni
        raw_share_SI = (1 - ni_share) * w_si
        share_sum = raw_share_NI + raw_share_SI
        no_shape = share_sum <= 0
        if no_shape.any():
            raw_share_NI = np.where(no_shape, ni_share, raw_share_NI)
            raw_share_SI = np.where(no_shape, 1 - ni_share, raw_share_SI)
            share_sum = raw_share_NI + raw_share_SI
        island_genload_NI = nat_gen * raw_share_NI / share_sum
        island_genload_SI = nat_gen * raw_share_SI / share_sum

        # Required transfer + symmetry check
        transfer_to_NI = island_genload_NI - g_NI
        transfer_to_SI = island_genload_SI - g_SI
        max_asym = np.abs(transfer_to_NI + transfer_to_SI).max()
        symmetry_report.append({"scenario": scenario, "year": year, "max_asymmetry_mwh": max_asym})

        # Capacity check
        viol = np.abs(transfer_to_NI) > HVDC_CAPACITY_MW
        if viol.any():
            capacity_flags.append({"scenario": scenario, "year": year, "n_hours": int(viol.sum()),
                                   "max_mw": float(np.abs(transfer_to_NI).max())})

        # Emissions attribution by exporting island
        import_NI = np.clip(transfer_to_NI, 0, None)
        export_NI = np.clip(-transfer_to_NI, 0, None)
        import_SI = np.clip(transfer_to_SI, 0, None)
        export_SI = np.clip(-transfer_to_SI, 0, None)

        efn = ef[(ef.scenario == scenario) & (ef.year == year) & (ef.ef_basis == "generation")]
        genEF_NI = efn[efn.island == "NI"].set_index("datetime_hour")["emission_factor_kg_co2e_per_kwh"].reindex(dt, fill_value=0.0).to_numpy()
        genEF_SI = efn[efn.island == "SI"].set_index("datetime_hour")["emission_factor_kg_co2e_per_kwh"].reindex(dt, fill_value=0.0).to_numpy()

        co2_NI = (g_NI - export_NI) * genEF_NI * 1000 + import_NI * genEF_SI * 1000  # kg
        co2_SI = (g_SI - export_SI) * genEF_SI * 1000 + import_SI * genEF_NI * 1000  # kg

        # national reconciliation: sum of consumed CO2 must equal original generation-side CO2
        orig_co2 = g_NI * genEF_NI * 1000 + g_SI * genEF_SI * 1000
        recon_diff = (co2_NI + co2_SI).sum() - orig_co2.sum()
        reconcile_report.append({"scenario": scenario, "year": year, "diff_kg": recon_diff,
                                 "diff_pct": (recon_diff / orig_co2.sum() * 100) if orig_co2.sum() else 0.0})

        with np.errstate(divide="ignore", invalid="ignore"):
            ef_NI = np.where(island_demand_NI > 0, co2_NI / (island_demand_NI * 1000), 0.0)
            ef_SI = np.where(island_demand_SI > 0, co2_SI / (island_demand_SI * 1000), 0.0)

        detail = (f"Island consumption EF: island demand (MBIE annual x Island share of demand x "
                 f"Assumption-1 per-island shape) vs generation reallocated via arithmetic "
                 f"inter-island transfer (island generation-level load renormalised to actual "
                 f"national generation, Step 2 fix - see edgs_common/README); {HIST_VALIDATION_NOTE} "
                 f"Emissions attributed by EXPORTING island's generation-side EF (Step 6).")
        cons_rows.append(pd.DataFrame({
            "scenario": scenario, "island": "NI", "datetime_hour": dt, "ef_basis": "consumption",
            "emission_factor_kg_co2e_per_kwh": ef_NI, "reconciliation_flag": "pending",
            "check2_deviation_pct": np.nan, "source_detail": detail}))
        cons_rows.append(pd.DataFrame({
            "scenario": scenario, "island": "SI", "datetime_hour": dt, "ef_basis": "consumption",
            "emission_factor_kg_co2e_per_kwh": ef_SI, "reconciliation_flag": "pending",
            "check2_deviation_pct": np.nan, "source_detail": detail}))

# Reports
sym = pd.DataFrame(symmetry_report)
log(f"\n=== Step 3: transfer symmetry check (135 scenario-years) ===")
log(f"  Max |transfer_to_NI + transfer_to_SI| across all scenario-years: "
    f"{sym.max_asymmetry_mwh.max():.2e} MWh (expect ~0, floating-point only, by renormalisation)")

log(f"\n=== Step 5: HVDC capacity check ({HVDC_SOURCE}) ===")
log("  CAVEAT (discovered during this brief): the raw EA/EMI Generation_MD data has NO "
    "'Solar' Fuel_Code at all before 2024 (checked 2021/2023 vs 2024 files directly) — a "
    "genuine historical data-availability gap, not a code bug. The shipped CENTRAL_TEMPLATE "
    "(2021) therefore has no solar hourly shape for NI or SI, and Module 4/5's existing, "
    "already-tagged fallback ('[A1 fallback: flat baseload]' in edgs_hourly_generation.parquet "
    "source_detail) spreads solar's annual GWh evenly across all 24 hours, including night. "
    "This does NOT affect annual totals (Check 1 still reconciles exactly) but DOES distort "
    "which specific hour is flagged as the worst transfer requirement below. The GROWING "
    "trend and large magnitude (order 1000s of MW vs the 1200 MW cited capacity, as national "
    "demand nearly doubles over the projection) is very unlikely to be solely a solar "
    "artifact, but the exact hour-by-hour numbers should be read as indicative, not precise. "
    "Fixing Module 4's solar shape (e.g. a synthetic diurnal curve, since no historical POC "
    "data exists for 2021-2023) is a separate, out-of-scope follow-up for this brief.")
if capacity_flags:
    cf = pd.DataFrame(capacity_flags)
    log(f"  FLAGGED: {len(cf)} scenario-years with |transfer| > {HVDC_CAPACITY_MW} MW in at least one hour:")
    log(cf.to_string(index=False))
else:
    log(f"  OK — no scenario-year-hour exceeds the cited {HVDC_CAPACITY_MW} MW capacity.")

rec = pd.DataFrame(reconcile_report)
log(f"\n=== Step 6: national reconciliation (island consumption CO2 sum vs generation-side CO2) ===")
log(f"  Max |diff_pct| across all scenario-years: {rec.diff_pct.abs().max():.10f}% "
    f"(mandatory check — must be ~0)")
if rec.diff_pct.abs().max() > 1e-6:
    log("  WARNING — reconciliation did not pass at floating-point precision; investigate before shipping.")
else:
    log("  OK — island consumption CO2 sums to the generation-side national CO2 total, exactly.")

# Write: append island consumption rows to the existing table (additive only)
cons_out = pd.concat(cons_rows, ignore_index=True)
# Idempotent: drop any island consumption rows from a PRIOR run of this script before
# appending fresh ones, so re-running never duplicates rows (national consumption + both
# generation bases are always left untouched).
existing = ef.drop(columns=["year"])
stale = (existing["ef_basis"] == "consumption") & (existing["island"].isin(["NI", "SI"]))
if stale.any():
    log(f"\nRemoving {stale.sum():,} stale island-consumption rows from a prior run before "
        f"appending fresh ones (idempotency).")
    existing = existing[~stale]
if "source_detail" not in existing.columns:
    existing["source_detail"] = ""
combined = pd.concat([existing, cons_out], ignore_index=True)
combined.to_parquet(OUT_DIR / "edgs_hourly_emission_factor.parquet", index=False)

sym.to_csv(OUT_DIR / "edgs_island_transfer_symmetry.csv", index=False)
rec.to_csv(OUT_DIR / "edgs_island_consumption_reconciliation.csv", index=False)
if capacity_flags:
    pd.DataFrame(capacity_flags).to_csv(OUT_DIR / "edgs_hvdc_capacity_flags.csv", index=False)

log(f"\nAdded {len(cons_out):,} island consumption rows to edgs_hourly_emission_factor.parquet "
    f"(now {len(combined):,} total rows, ef_basis values: {sorted(combined.ef_basis.unique())}, "
    f"islands: {sorted(combined.island.unique())})")
(OUT_DIR / "processing_log_island_consumption.txt").write_text("\n".join(lines), encoding="utf-8")

# Append a section to the shared README (Module 6 writes the base document; this module
# runs after it and appends, rather than duplicating Module 6's f-string logic here).
n_cap_flag_years = len(capacity_flags)
max_transfer_mw = max((c["max_mw"] for c in capacity_flags), default=0.0)
readme_addendum = f"""

## Island-resolved consumption-side emission factor (Module 7)

Adds `ef_basis='consumption'` rows for `island='NI'` and `island='SI'` to
edgs_hourly_emission_factor.parquet, alongside the unchanged National consumption row. The
three "not quite fully assumption-free" points, together:

1. **Step 2 simplification, CORRECTED from the brief's literal formula.** The literal
   `island_demand(t) x national_grossup_factor` formula was implemented and tested first; it
   produced a genuine national hourly imbalance (std ~383 MWh, max ~1713 MWh, ~27.6% of mean
   hourly demand for a sample scenario-year) — NOT rounding error. Cause: Module 5's thermal
   dispatch sets each fuel's ANNUAL total to MBIE's published figure while only the SHAPE
   (not the absolute level) follows the demand-minus-renewables residual; since 100% of
   thermal capacity is NI, this manifests as a national-level gap between the demand-scaled
   load series and actually-dispatched generation. FIX: island generation-level load is
   renormalised so the NATIONAL total exactly equals ACTUAL national generation(t) at every
   hour (the grossup factor cancels out of the per-island SPLIT ratio, which still comes
   entirely from MBIE's Island share of demand and Assumption 1's per-island shape — no new
   data source). This guarantees the Step 3 transfer-symmetry check holds at floating-point
   precision (confirmed: max |transfer_to_NI + transfer_to_SI| = 3.18e-12 MWh across all
   135 scenario-years, after also fixing a single DST-transition-hour edge case).
2. **Reliance on arithmetic balance, not directly observed future HVDC data** — inherent to
   any forward-looking method: there is no way to observe 2024-2050 HVDC dispatch directly,
   so the required transfer is computed as island generation-level load minus island
   generation, not modelled from real inter-island trading/frequency-keeping behaviour.
3. **Step 4 historical validation result that (partially) justifies trusting (2):** the
   literal test (historical demand minus generation vs real net_to_NI_MWh) is a TAUTOLOGY,
   not independent evidence — the historical Consumption pipeline DEFINES "consumption" as
   generation + real metered transfer, so the two match by construction (confirmed: diff at
   floating-point precision, 4.55e-13 MWh). No independently-metered per-island demand
   dataset exists locally to run a true independent test. The only genuinely independent
   check available: real historical HVDC direction (SI net-exports to NI in 77.0% of hours)
   matches NZ's well-documented SI hydro surplus — a plausibility check only, not a
   precision validation. **This means the forward-looking transfer/consumption-EF numbers
   should be read as an internally-consistent accounting method, not as a validated
   prediction of actual future HVDC dispatch.**

**Step 5 — HVDC capacity check.** Cited: Transpower, "HVDC link upgrade programme"
(transpower.co.nz/hvdc-upgrade, accessed 2026-07) — current rated capacity 1200 MW
(cable-limited); a 1400 MW upgrade (4th submarine cable, Stage 1) was approved by the
Commerce Commission 18 June 2026 ($1.1bn), expected to complete in the early 2030s — verified (Brief D)
against both Transpower's own page and the Commerce Commission decision independently, not
assumed. **{n_cap_flag_years} of 135 scenario-years have at least one hour where the
required transfer exceeds 1200 MW** (up to {max_transfer_mw:.0f} MW by 2050 in some
scenarios), concentrated in later years and lower-thermal scenarios, as national demand
nearly doubles over the projection while HVDC capacity is held fixed at the cited figure.
This is reported as a flag, NOT silently clipped or rescaled — it signals a structural
tension between MBIE's own demand/generation projections and a fixed transfer-capacity
assumption that this pipeline does not otherwise model (e.g. MBIE's projections may
implicitly assume additional local generation buildout, transmission upgrades, or a
different balancing pattern). A CAVEAT discovered during this brief: the raw EA/EMI data
has no 'Solar' Fuel_Code before 2024, so the shipped central template (2021) has no solar
hourly shape and Module 5's existing fallback spreads solar flat across all 24 hours — this
distorts which specific hour is flagged, though not annual totals, and is unlikely to be
the sole driver of the trend. Detail: edgs_hvdc_capacity_flags.csv.

**Step 6 — emissions attributed by exporting island**, national reconciliation (island
consumption CO2 sums to the generation-side national CO2 total) verified EXACT for all 135
scenario-years (max |diff| = {rec.diff_pct.abs().max():.10f}%). Detail:
edgs_island_consumption_reconciliation.csv, edgs_island_transfer_symmetry.csv.

**Known limitation carried over, not fixed here:** Assumption 2's DSR/battery is booked
100% to NI in the existing generation table even though GEM build schedule capacity is
split ~48%/52% NI/SI — this is the separately-flagged battery/BESS capacity gap priority,
not addressed in this module.
"""
readme_path = OUT_DIR / "README_EDGS_hourly.md"
if readme_path.exists():
    txt = readme_path.read_text(encoding="utf-8")
    marker = "## Island-resolved consumption-side emission factor (Module 7)"
    if marker in txt:
        txt = txt.split(marker)[0].rstrip()  # idempotent: drop a stale prior addendum
    readme_path.write_text(txt + readme_addendum, encoding="utf-8")
    log("Appended Module 7 section to README_EDGS_hourly.md (idempotent)")
