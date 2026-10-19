"""
Shared fuel and emission-factor attribution for the metered pipeline.

Replaces the per-script lookup that took the unweighted mean of every active register record
for a (POC, fuel) pair. Factors are resolved by generator code and register unit, with the
sourced overrides in fuel_attribution_overrides.csv (one row per override, with source, page
and URL):

  Huntly Units 1-4    split into coal and gas by Genesis Energy's quarterly Rankine coal share,
                      uniform within the quarter. Coal portion at the register coal record
                      (994.08 kg/MWh); gas portion at the Rankine heat rate x register gas
                      factor (575.52 kg/MWh, ESTIMATE). 2015 Q1-Q2: share = Genesis coal GWh /
                      metered Rankine GWh, capped at 1. No Genesis figure: all coal, flagged.
  Unit mapping        huntly_e3p -> HLY5, huntly_p40 -> HLY6, rotokawa -> RKA0, tehuka -> TAA0.
  Decommissioned      a register record is inactive after its DateDecommissioned (Southdown 5).
  Kinleith            fuel Wood; EF = projection wood CH4+N2O factor (1.52 kg/GJ) x MBIE wood
                      fuel input / wood generation for the year (ESTIMATE).
  Stratford           primary series stays pooled; two bound columns (combined cycle SPL0,
                      peaker SFD21) are carried alongside.
  Matahina            generation filled from Manawa Energy fiscal-year station totals (FY23,
                      FY24) and, for April 2024 to December 2025, the independent adviser's
                      long-term average (not measured). Every value is flagged with its
                      fill_basis; see matahina_fill().

Everything else keeps the previous rule: mean of the active register records for (POC, fuel).
Non-thermal fuels carry EF 0, except Wood (Kinleith) as above.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from geothermal_ef_correction import apply_geothermal_ef_correction

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OVERRIDES_FILE = HERE / "fuel_attribution_overrides.csv"
PLANT_FILE = ROOT / "EA data" / "Dispatched generation plant.csv"
EDGS_RESULTS = ROOT / "edgs_pipeline" / "EDGS_2024_Results.xlsx"
GEN_DIR = ROOT / "EA_EMI_raw"

THERMAL_FUELS = {"CLG", "GAS", "DSL", "GEO"}
KEY = ["poc", "gen_code", "fuel_std", "year", "month"]
FUEL_STD = {"Coal": "CLG", "CLG": "CLG", "Gas": "GAS", "GAS": "GAS", "Diesel": "DSL", "DSL": "DSL",
            "Geo": "GEO", "GEO": "GEO", "Hydro": "HYD", "HYD": "HYD", "Solar": "SOL", "SOL": "SOL",
            "Wind": "WIN", "WIN": "WIN", "Wood": "WOOD", "ELE": "ELE"}
NSP_DIR = ROOT / "EA data" / "NSP Tables"


def poc_island_map():
    """POC -> 'NI'/'SI' from the NSP tables, latest record per POC (as build_ef_timeseries.py)."""
    nsp = pd.concat([pd.read_csv(f, low_memory=False) for f in sorted(NSP_DIR.glob("*_NetworkSupplyPointsTable.csv"))],
                    ignore_index=True)
    nsp = nsp.drop_duplicates(subset=["POC code", "Reconciliation type", "Island", "Start date", "End date"])
    return (nsp.dropna(subset=["Island"]).sort_values("Start date", ascending=False)
            .drop_duplicates(subset=["POC code"]).set_index("POC code")["Island"].to_dict())


def load_register(mfe_t_per_tj=None, heat_rate_overrides=None, technology_overrides=None):
    """Register with active-period dates and EF_kg_per_MWh. With mfe_t_per_tj ({FuelCode:
    t CO2/TJ}), combustion EF = register HeatRate x MfE factor instead of the register's own
    EmissionsFactor (MFE_FACTOR_* overrides)."""
    p = pd.read_csv(PLANT_FILE, low_memory=False)
    p["eff_start"] = pd.to_datetime(p["effective_start_datetime"], utc=True, errors="coerce")
    end = p["effective_end_datetime"].astype(str).str.replace(r"^9999-.*$", "2200-01-01T00:00:00.000Z", regex=True)
    p["eff_end"] = pd.to_datetime(end, utc=True, errors="coerce")
    # RULE_DECOMMISSIONED: a record is not active after its DateDecommissioned.
    dec = pd.to_datetime(p["DateDecommissioned"], dayfirst=True, errors="coerce", utc=True)
    p["eff_end"] = p["eff_end"].where(dec.isna() | (p["eff_end"] <= dec), dec)
    # HEATRATE_* overrides ({(POC, UnitCode): GJ/GWh}) replace the register heat rate first.
    for (poc, unit), hr in (heat_rate_overrides or {}).items():
        sel = (p["PointOfConnectionCode"] == poc) & (p["UnitCode"] == unit)
        if not sel.any():
            raise ValueError(f"heat-rate override: no register record for {poc} {unit}")
        p.loc[sel, "HeatRate"] = hr
    # TECH_* overrides ({(POC, UnitCode): Technology}) correct the recorded plant type
    for (poc, unit), tech in (technology_overrides or {}).items():
        sel = (p["PointOfConnectionCode"] == poc) & (p["UnitCode"] == unit)
        if not sel.any():
            raise ValueError(f"technology override: no register record for {poc} {unit}")
        p.loc[sel, "Technology"] = tech
    p["EF_kg_per_MWh"] = p["HeatRate"] * p["EmissionsFactor"] / 1e6
    apply_geothermal_ef_correction(p)
    if mfe_t_per_tj:
        comb = p["FuelCode"].isin(list(mfe_t_per_tj))
        # HeatRate (GJ/GWh) x factor (t/TJ) / 1000 = kg/MWh
        p.loc[comb, "EF_kg_per_MWh"] = p.loc[comb, "HeatRate"] * p.loc[comb, "FuelCode"].map(mfe_t_per_tj) / 1000.0
    return p


class FuelAttribution:
    def __init__(self, mfe_factors=True, nzga_geothermal=True, glenbrook_zero=True, heat_rate_fixes=True):
        self.ov = pd.read_csv(OVERRIDES_FILE, dtype={"value": str})
        o = self.ov.set_index("override_id")
        self.mfe = {r.parameter.split("_")[-1]: float(r.value) for r in self.ov.itertuples()
                    if r.override_id.startswith("MFE_FACTOR_")} if mfe_factors else None
        hro = {(r.poc, r.parameter.split("_")[-1]): float(r.value) for r in self.ov.itertuples()
               if r.override_id.startswith("HEATRATE_")} if heat_rate_fixes else None
        tech = {(r.poc, r.parameter.split("_")[-1]): r.value for r in self.ov.itertuples()
                if r.override_id.startswith("TECH_")} if heat_rate_fixes else None
        self.reg = load_register(self.mfe, hro, tech)
        self.unit_map = {r.gen_code: r.value for r in self.ov.itertuples()
                         if r.override_id.startswith("UNIT_")}
        self.coal_unit = o.loc["HUNTLY_COAL_PORTION_EF", "value"]
        if self.mfe:  # Rankine heat rate x MfE gas factor (same estimate, MfE factor)
            hr = float(self.reg[self.reg.UnitCode == self.coal_unit].HeatRate.iloc[0])
            self.gas_portion_ef = hr * self.mfe["GAS"] / 1000.0
        else:
            self.gas_portion_ef = float(o.loc["HUNTLY_GAS_PORTION_EF", "value"])
        self.nzga = None
        if nzga_geothermal:
            t = pd.read_csv(HERE / "geothermal_intensity_nzga.csv")
            self.nzga = {(r.station, int(r.year)): float(r.g_co2e_per_kwh) for r in t.itertuples()}
            # gen_code -> [(start, end, station)]; blank dates mean open-ended
            self.geo_map = {}
            for r in self.ov[self.ov.override_id.str.startswith("GEO_MAP_")].itertuples():
                s = pd.Timestamp(r.period_start) if isinstance(r.period_start, str) and r.period_start else pd.Timestamp.min
                e = pd.Timestamp(r.period_end) if isinstance(r.period_end, str) and r.period_end else pd.Timestamp.max
                self.geo_map.setdefault(r.gen_code, []).append((s, e, r.value))
        self.glenbrook_zero = glenbrook_zero
        if glenbrook_zero:
            gb = self.reg[(self.reg.PointOfConnectionCode == "GLN0332") & (self.reg.FuelCode == "GAS")]
            gas = self.mfe["GAS"] if self.mfe else float(gb.EmissionsFactor.iloc[0]) / 1000.0
            self.glenbrook_bound_ef = float(gb.HeatRate.iloc[0]) * gas / 1000.0
        self.bound_units = {"ccgt": o.loc["STRATFORD_BOUND_CCGT", "value"],
                            "peaker": o.loc["STRATFORD_BOUND_PEAKER", "value"]}
        self.wood_kg_per_gj = float(o.loc["KINLEITH_WOOD", "value"])
        hc = self.ov[self.ov.override_id.str.match(r"HUNTLY_COAL_\d{4}Q\d")]
        self.huntly = {r.override_id[-6:]: (r.parameter, float(r.value)) for r in hc.itertuples()}
        self.wood_hr = self._wood_heat_rate()

    # Register lookups
    def _active(self, recs, year, month):
        ref = pd.Timestamp(f"{year}-{month:02d}-15", tz="UTC")
        a = recs[(recs.eff_start <= ref) & (ref < recs.eff_end) & recs.EF_kg_per_MWh.notna()]
        return float(a.EF_kg_per_MWh.mean()) if len(a) else 0.0

    def pooled_ef(self, poc, fuel, year, month):
        r = self.reg
        return self._active(r[(r.PointOfConnectionCode == poc) & (r.FuelCode == fuel)], year, month)

    def unit_ef(self, unit, year, month):
        return self._active(self.reg[self.reg.UnitCode == unit], year, month)

    def _wood_heat_rate(self):
        """MBIE wood fuel input / wood net generation per year, GJ/MWh (Reference for projections)."""
        u = pd.read_excel(EDGS_RESULTS, sheet_name="Electricity generation")
        w = u[(u.Commodity == "Wood") & (u.Scenario == "Reference")]
        pj = w[w.Variable == "Electricity generation use"].set_index("TimePeriod").Value
        gwh = w[w.Variable == "Net electricity generation"].set_index("TimePeriod").Value
        return (pj * 1e6 / (gwh * 1e3)).dropna().to_dict()  # GJ / MWh

    # Per-key parts
    def factor_parts(self, gen):
        """One or two rows per (poc, gen_code, fuel_std, year, month) key present in gen, each
        with fuel_out, share, ef, bound EFs, estimated flag and the rule applied."""
        keys = gen[KEY].drop_duplicates()
        rankine_q = self._rankine_quarter_gwh(gen)
        rows = []
        for poc, gc, fuel, y, m in keys.itertuples(index=False):
            y, m = int(y), int(m)
            if gc == "huntly_1_4" and fuel == "CLG":
                q = f"{y}Q{(m - 1) // 3 + 1}"
                coal_ef = self.unit_ef(self.coal_unit, y, m)
                if q in self.huntly:
                    kind, v = self.huntly[q]
                    if kind == "genesis_coal_GWh":
                        metered = rankine_q.get(q, 0.0)
                        share = min(1.0, v / metered) if metered > 0 else 1.0
                    else:
                        share = v
                    rule, est_coal = f"HUNTLY_COAL_{q}", False
                else:
                    share, rule, est_coal = 1.0, "HUNTLY_NO_SHARE_FALLBACK", True
                rows.append((poc, gc, fuel, y, m, "CLG", share, coal_ef, coal_ef, coal_ef, coal_ef, est_coal, rule))
                if share < 1.0:
                    g = self.gas_portion_ef
                    rows.append((poc, gc, fuel, y, m, "GAS", 1.0 - share, g, g, g, g, True, "HUNTLY_GAS_PORTION_EF"))
                continue
            est = fuel == "WOOD"
            glen = None
            if fuel == "GEO" and self.nzga is not None:
                # Proxy rule (RULE_GEO_PROXY_ORDER): (1) source-specific figure; (2) the same
                # station's nearest published year; (3) nearest station on the same field (a
                # GEO_MAP_ row); (4) NZGA fleet average. 2025 rows hold 2024 flat.
                w = self._geo_weights(gc, poc, y, m)
                vals = {st: self._nzga_nearest(st, y) for st in w}
                if not w or any(v is None for v in vals.values()):
                    ef = self._nzga_nearest("NZGA MW-weighted average", y)[0]
                    rule, est = "GEO_FALLBACK_NZGA_AVERAGE", True
                else:
                    ef = sum(vals[st][0] * w[st] for st in w)
                    step2 = any(vals[st][1] for st in w)
                    rule = "GEO_NZGA_" + "+".join(w) + ("_NEARESTYEAR" if step2 else "")
                    est = y >= 2025 or len(w) > 1 or step2
            elif gc == "glenbrook_kilns" and fuel == "GAS" and self.glenbrook_zero:
                ef, rule, glen = 0.0, "GLENBROOK_ZERO", self.glenbrook_bound_ef
            elif gc in self.unit_map and fuel in THERMAL_FUELS:
                ef, rule = self.unit_ef(self.unit_map[gc], y, m), f"UNIT_{self.unit_map[gc]}"
            elif fuel == "WOOD":
                hr = self.wood_hr.get(y, self.wood_hr[max(self.wood_hr)])
                ef, rule = self.wood_kg_per_gj * hr, "KINLEITH_WOOD"
            elif fuel in THERMAL_FUELS:
                ef, rule = self.pooled_ef(poc, fuel, y, m), "POOLED"
            else:
                ef, rule = 0.0, "NON_THERMAL"
            lo = hi = ef
            if gc == "stratford" and fuel == "GAS":
                lo = self.unit_ef(self.bound_units["ccgt"], y, m)
                hi = self.unit_ef(self.bound_units["peaker"], y, m)
            rows.append((poc, gc, fuel, y, m, fuel, 1.0, ef, lo, hi, ef if glen is None else glen, est, rule))
        return pd.DataFrame(rows, columns=KEY + ["fuel_out", "share", "ef_kg_per_mwh", "ef_bound_ccgt",
                                                 "ef_bound_peaker", "ef_bound_glenbrook", "estimated", "rule"])

    def _nzga_nearest(self, st, y):
        """(g/kWh, used_other_year) for a station: its own year if published, else its nearest
        published year (earlier year on a tie); None if the station has no figure at all."""
        if (st, y) in self.nzga:
            return self.nzga[(st, y)], False
        yrs = sorted(yy for ss, yy in self.nzga if ss == st)
        if not yrs:
            return None
        yy = min(yrs, key=lambda k: (abs(k - y), k))
        return self.nzga[(st, yy)], True

    def _geo_weights(self, gc, poc, y, m):
        """{station: weight} for a geothermal generator-month. One mapping covers the month:
        weight 1. A mapping change inside the month: weights are that generator's metered
        Generation_MD output before and after the change date (days if no metered output)."""
        ms = pd.Timestamp(y, m, 1)
        me = ms + pd.offsets.MonthEnd(0)
        spans = [(max(s, ms), min(e, me), st) for s, e, st in self.geo_map.get(gc, []) if s <= me and e >= ms]
        if len(spans) <= 1:
            return {st: 1.0 for _, _, st in spans}
        f = GEN_DIR / f"{y}{m:02d}_Generation_MD.csv"
        daily = None
        if f.exists():
            d = pd.read_csv(f, low_memory=False)
            d = d[(d.Gen_Code == gc) & (d.POC_Code == poc)]
            date_col = {c.lower(): c for c in d.columns}["trading_date"]
            tp = [c for c in d.columns if re.match(r"^TP\d+$", c)]
            daily = d.groupby(pd.to_datetime(d[date_col]))[tp].sum().sum(axis=1)
        w = {}
        for s, e, st in spans:
            days = pd.date_range(s.normalize(), e.normalize(), freq="D")
            v = float(daily.reindex(days).fillna(0).sum()) if daily is not None and daily.sum() > 0 else float(len(days))
            w[st] = w.get(st, 0.0) + v
        tot = sum(w.values())
        return {st: v / tot for st, v in w.items()}

    def blended_ef(self, gen):
        """One factor per (poc, gen_code, fuel_std, year, month) key: CO2 / generation, i.e. the
        share-weighted factor where a key is split (Huntly 1-4 coal/gas). For scripts that need
        a factor lookup at trading-period level. gen must carry real gen_mwh with every month
        of each quarter it covers (the 2015 Q1-Q2 Huntly share uses metered quarterly output)."""
        g = gen[KEY + ["gen_mwh"]].groupby(KEY, as_index=False).gen_mwh.sum()
        # attribute() splits a key into parts and relabels each part's fuel_std (Huntly 1-4:
        # CLG -> CLG + GAS), so CO2 is summed back by row, not by KEY. Summing by KEY dropped
        # the GAS part's CO2 (fixed in ef-database-v1.0.1).
        g["_row"] = np.arange(len(g))
        a = self.attribute(g.copy())
        c = g.assign(co2_kg=g["_row"].map(a.groupby("_row").co2_kg.sum()).fillna(0.0)).drop(columns="_row")
        c["ef_kg_per_mwh"] = np.where(c.gen_mwh != 0, c.co2_kg / c.gen_mwh.where(c.gen_mwh != 0, 1.0), 0.0)
        # zero-generation keys: fall back to the unweighted factor
        z = c.gen_mwh == 0
        if z.any():
            p = self.factor_parts(c.loc[z, KEY].assign(gen_mwh=0.0))
            p["w"] = p["share"] * p["ef_kg_per_mwh"]
            zf = p.groupby(KEY, as_index=False).w.sum()
            c = c.merge(zf, on=KEY, how="left")
            c.loc[z, "ef_kg_per_mwh"] = c.loc[z, "w"]
            c = c.drop(columns="w")
        return c[KEY + ["ef_kg_per_mwh"]]

    def generation(self, level="month", include_fills=True, exclude_cogen=False, months=None):
        """Generation_MD rows (plus the flagged fills) as poc, gen_code, fuel_std, tech_code,
        year, month, [trading_date], [tp], gen_mwh, filled. level: 'month', 'day' or 'tp'
        (TP1-TP50). months: optional iterable of 'YYYYMM'. exclude_cogen drops EMI Tech_Code
        'Cogen' rows (fills are never cogeneration). Island is not assigned here."""
        parts = []
        for f in sorted(GEN_DIR.glob("*_Generation_MD.csv")):
            ym = f.name[:6]
            if months is not None and ym not in set(months):
                continue
            d = pd.read_csv(f, low_memory=False)
            cols = {c.lower(): c for c in d.columns}
            tp = [f"TP{i}" for i in range(1, 51) if f"TP{i}" in d.columns]
            d = d.rename(columns={cols["poc_code"]: "poc", cols["gen_code"]: "gen_code", cols["fuel_code"]: "fuel_code_raw",
                                  cols.get("tech_code", "Tech_Code"): "tech_code", cols["trading_date"]: "trading_date"})
            if "tech_code" not in d:
                d["tech_code"] = ""
            if exclude_cogen:
                d = d[d["tech_code"].astype(str).str.lower() != "cogen"]
            d["trading_date"] = pd.to_datetime(d["trading_date"])
            if level == "tp":
                m = d.melt(id_vars=["poc", "gen_code", "fuel_code_raw", "tech_code", "trading_date"], value_vars=tp,
                           var_name="tp", value_name="kwh").dropna(subset=["kwh"])
                m["tp"] = m["tp"].str[2:].astype(int)
                m["gen_mwh"] = m.pop("kwh") / 1000.0
                keys = ["poc", "gen_code", "fuel_code_raw", "tech_code", "trading_date", "tp"]
                parts.append(m.groupby(keys, as_index=False).gen_mwh.sum())
            else:
                d["gen_mwh"] = d[tp].sum(axis=1, skipna=True) / 1000.0
                keys = ["poc", "gen_code", "fuel_code_raw", "tech_code"] + (["trading_date"] if level == "day" else [])
                if level == "month":
                    d["trading_date"] = pd.Timestamp(f"{ym[:4]}-{ym[4:]}-01")
                    keys = keys + ["trading_date"]
                parts.append(d.groupby(keys, as_index=False).gen_mwh.sum())
        g = pd.concat(parts, ignore_index=True)
        g["filled"] = False
        if include_fills:
            fl = self.fills()
            if months is not None:
                fl = fl[fl.trading_date.dt.strftime("%Y%m").isin(set(months))]
            fl = fl[fl.trading_date.dt.strftime("%Y%m").isin(set(g.trading_date.dt.strftime("%Y%m")))]
            fl = fl.assign(tech_code="fill", filled=True)
            if level == "tp":
                fl = fl.groupby(["poc", "gen_code", "fuel_code_raw", "tech_code", "trading_date", "tp"], as_index=False).gen_mwh.sum()
            else:
                if level == "month":
                    fl["trading_date"] = fl.trading_date.dt.to_period("M").dt.start_time
                fl = fl.groupby(["poc", "gen_code", "fuel_code_raw", "tech_code", "trading_date"], as_index=False).gen_mwh.sum()
            fl["filled"] = True
            g = pd.concat([g, fl], ignore_index=True)
        g["fuel_std"] = g["fuel_code_raw"].map(FUEL_STD).fillna(g["fuel_code_raw"])
        g["year"] = g["trading_date"].dt.year
        g["month"] = g["trading_date"].dt.month
        if level == "month":
            g = g.drop(columns="trading_date")
        return g

    @staticmethod
    def _rankine_quarter_gwh(gen):
        h = gen[gen.gen_code == "huntly_1_4"]
        q = h["year"].astype(int).astype(str) + "Q" + ((h["month"].astype(int) - 1) // 3 + 1).astype(str)
        return (h.groupby(q)["gen_mwh"].sum() / 1000.0).to_dict()

    def attribute(self, gen):
        """gen: rows with KEY columns and gen_mwh (plus any pass-through columns). Returns rows
        split where needed, with fuel_std replaced by the attributed fuel and co2 columns added."""
        parts = self.factor_parts(gen)
        out = gen.merge(parts, on=KEY, how="left", validate="many_to_many")
        if out["ef_kg_per_mwh"].isna().any():
            raise RuntimeError("fuel_attribution: rows without a factor")
        out["gen_mwh"] = out["gen_mwh"] * out["share"]
        out["fuel_std"] = out.pop("fuel_out")
        out["co2_kg"] = out["gen_mwh"] * out["ef_kg_per_mwh"]
        out["co2_kg_bound_ccgt"] = out["gen_mwh"] * out["ef_bound_ccgt"]
        out["co2_kg_bound_peaker"] = out["gen_mwh"] * out["ef_bound_peaker"]
        out["co2_kg_bound_glenbrook"] = out["gen_mwh"] * out["ef_bound_glenbrook"]
        out["co2_kg_estimated"] = np.where(out["estimated"], out["co2_kg"], 0.0)
        return out.drop(columns=["share", "ef_bound_ccgt", "ef_bound_peaker", "ef_bound_glenbrook"])

    # Matahina fill
    def matahina_fill(self):
        """Trading-period rows for Matahina from Manawa fiscal-year totals (Apr-Mar).
        Returns trading_date, tp (1-48), gen_mwh, override_id. Hydro, EF 0, all flagged.
        Since 2026-09-29 no MATAHINA_ rows remain (superseded by GRIDIMPORT_FILL_MAT1101)."""
        if not self.ov.override_id.str.startswith("MATAHINA_").any():
            return pd.DataFrame([], columns=["trading_date", "tp", "gen_mwh", "override_id", "fill_basis"])
        parts = []
        for f in sorted(GEN_DIR.glob("*_Generation_MD.csv")):
            if not ("201501" <= f.name[:6] <= "202112"):
                continue
            d = pd.read_csv(f, low_memory=False)
            d = d[d.Gen_Code == "matahina"]
            if d.empty:
                continue
            date_col = {c.lower(): c for c in d.columns}["trading_date"]
            tp = [f"TP{i}" for i in range(1, 49)]
            m = d.groupby(date_col)[tp].sum() / 1000.0  # MWh per TP per day
            m.index = pd.to_datetime(m.index)
            parts.append(m)
        hist = pd.concat(parts).groupby(level=0).sum().sort_index()
        daily = hist.sum(axis=1)
        monthly = daily.groupby([daily.index.year, daily.index.month]).sum()
        monthly.index.names = ["year", "month"]
        # FY (Apr-Mar) monthly shares over complete FYs FY2016-FY2021 (Apr 2015 - Mar 2021)
        shares = []
        for fy in range(2016, 2022):
            months = [(fy - 1, mm) for mm in range(4, 13)] + [(fy, mm) for mm in range(1, 4)]
            v = pd.Series({mm: monthly.get((yy, mm), np.nan) for yy, mm in months})
            shares.append(v / v.sum())
        fy_share = pd.concat(shares, axis=1).mean(axis=1)
        fy_share = fy_share / fy_share.sum()
        # mean TP-of-day profile per calendar month, 2015-2021
        tp_prof = hist.groupby(hist.index.month).mean()
        tp_prof = tp_prof.div(tp_prof.sum(axis=1), axis=0)
        rows = []
        for r in self.ov[self.ov.override_id.str.startswith("MATAHINA_")].itertuples():
            # value is an annual (Apr-Mar) total; each month in [period_start, period_end]
            # takes its FY share of it, so a partial-year row fills only its own months.
            start, end = pd.Timestamp(r.period_start), pd.Timestamp(r.period_end)
            total_mwh = float(r.value) * 1000.0
            for ms in pd.date_range(start, end, freq="MS"):
                month_mwh = total_mwh * fy_share[ms.month]
                days = pd.date_range(ms, ms + pd.offsets.MonthEnd(0), freq="D")
                day_mwh = month_mwh / len(days)
                prof = tp_prof.loc[ms.month].to_numpy()
                for day in days:
                    p = prof
                    if day.month == 9 and day.weekday() == 6 and day.day > 23:
                        # DST spring-forward day (last Sunday of September): 46 trading
                        # periods; TP47/TP48 do not exist, so none are filled.
                        p = np.concatenate([prof[:46] / prof[:46].sum(), [0.0, 0.0]])
                    for i, s in enumerate(p, start=1):
                        if s > 0 or i <= 46:
                            rows.append((day, i, day_mwh * s, r.override_id, r.fill_basis))
        return pd.DataFrame(rows, columns=["trading_date", "tp", "gen_mwh", "override_id", "fill_basis"])

    # Huntly 1-4 fill for months missing from Generation_MD
    def huntly_fill(self):
        """HUNTLY_FILL_* overrides: value = Genesis quarterly Rankine output (GWh). The missing
        month gets that total minus the metered huntly_1_4 output of the quarter's other months,
        shaped by those months' mean trading-period-of-day profile, flat across days."""
        rows = []
        for r in self.ov[self.ov.override_id.str.startswith("HUNTLY_FILL_")].itertuples():
            start, end = pd.Timestamp(r.period_start), pd.Timestamp(r.period_end)
            q0 = start.to_period("Q").start_time
            others = [m for m in pd.date_range(q0, q0 + pd.offsets.QuarterEnd(0), freq="MS") if m != start]
            parts = []
            for m in others:
                d = pd.read_csv(GEN_DIR / f"{m:%Y%m}_Generation_MD.csv", low_memory=False)
                d = d[d.Gen_Code == "huntly_1_4"]
                date_col = {c.lower(): c for c in d.columns}["trading_date"]
                parts.append(d.groupby(date_col)[[f"TP{i}" for i in range(1, 49)]].sum() / 1000.0)
            hist = pd.concat(parts)
            metered_mwh = hist.to_numpy().sum()
            fill_mwh = float(r.value) * 1000.0 - metered_mwh
            prof = hist.mean().to_numpy()
            prof = prof / prof.sum()
            days = pd.date_range(start, end, freq="D")
            for day in days:
                p = prof
                if day.month == 9 and day.weekday() == 6 and day.day > 23:
                    p = np.concatenate([prof[:46] / prof[:46].sum(), [0.0, 0.0]])
                for i, s in enumerate(p, start=1):
                    if s > 0 or i <= 46:
                        rows.append((day, i, fill_mwh / len(days) * s, r.override_id, r.fill_basis))
        return pd.DataFrame(rows, columns=["trading_date", "tp", "gen_mwh", "override_id", "fill_basis"])

    # Grid_import fill for generators missing from Generation_MD
    @staticmethod
    def _tp_frame(kind, ym, poc_col, poc, extra=None):
        """Trading-period MWh by date (TP1-TP50) at one POC from one monthly EMI file."""
        f = GEN_DIR / f"{ym}_{kind}.csv"
        if not f.exists():
            return None
        d = pd.read_csv(f, low_memory=False)
        cols = {c.lower(): c for c in d.columns}
        d = d[d[cols[poc_col.lower()]] == poc]
        if extra:
            for k, v in extra.items():
                d = d[d[cols[k.lower()]] == v]
        tp = [f"TP{i}" for i in range(1, 51) if f"TP{i}" in d.columns]
        g = d.groupby(pd.to_datetime(d[cols["trading_date"]]))[tp].sum() / 1000.0
        return g.reindex(columns=[f"TP{i}" for i in range(1, 51)], fill_value=0.0).fillna(0.0)

    def _poc_total(self, kind, ym, poc_col, poc):
        """Monthly MWh at a POC (None if the file does not exist), cached."""
        cache = self.__dict__.setdefault("_tot_cache", {})
        k = (kind, ym, poc)
        if k not in cache:
            f = self._tp_frame(kind, ym, poc_col, poc)
            cache[k] = None if f is None else float(f.to_numpy().sum())
        return cache[k]

    def _gm_gi_ratio(self, poc, ym):
        """Generation_MD / Grid_import at a POC: mean over the nearest month before and the
        nearest month after ym where both files have that POC (whichever exist)."""
        months = pd.period_range("2015-01", "2026-12", freq="M")
        target = pd.Period(ym, "M")
        found = []
        for direction in (-1, 1):
            p = target + direction
            while p in months:
                gm = self._poc_total("Generation_MD", p.strftime("%Y%m"), "POC_Code", poc)
                gi = self._poc_total("Grid_import", p.strftime("%Y%m"), "POC", poc)
                if gm and gi:
                    found.append((p.strftime("%Y%m"), gm / gi))
                    break
                if gm is None and gi is None:
                    break
                p += direction
        if not found:
            raise RuntimeError(f"no month with both Generation_MD and Grid_import at {poc}")
        return float(np.mean([r for _, r in found])), found

    def grid_import_fill(self, others=None):
        """GRIDIMPORT_FILL_* overrides: Grid_import injection at the POC x the POC's Generation_MD /
        Grid_import ratio in the nearest months with both, less other generators' metered or
        filled output at that POC (others: trading-period fill rows already built), split
        between the row's generators by their metered shares over split_months (value:
        'gen_code;gen_code|YYYY-MM;YYYY-MM', blank split for a single generator). Trading-period
        shape from Grid_import itself; negative residual periods are set to zero and the rest
        rescaled to the monthly residual total. Flagged 'Grid_import, scaled'.
        An optional third field selects Grid_import streams ('Generation_Type=GG'). A parameter
        starting 'grid_import_measured' takes the stream as measured (ratio 1, no scaling): used
        where that stream equals Generation_MD for the generator in every month both exist.
        Flagged 'Grid_import, measured'."""
        rows, self.grid_import_log = [], []
        for r in self.ov[self.ov.override_id.str.startswith("GRIDIMPORT_FILL_")].itertuples():
            gens, _, rest = r.value.partition("|")
            split, _, stream = rest.partition("|")
            gens = gens.split(";")
            extra = dict(kv.split("=") for kv in stream.split(";") if kv)
            measured = r.parameter.startswith("grid_import_measured")
            shares = {gens[0]: 1.0}
            if split:
                tot = {g: 0.0 for g in gens}
                for ym in split.split(";"):
                    gm = pd.read_csv(GEN_DIR / f"{ym.replace('-', '')}_Generation_MD.csv", low_memory=False)
                    gm = gm[(gm.POC_Code == r.poc) & gm.Gen_Code.isin(gens)]
                    tp = [c for c in gm.columns if re.match(r"^TP\d+$", c)]
                    for g in gens:
                        tot[g] += np.nansum(gm.loc[gm.Gen_Code == g, tp].to_numpy(dtype=float))
                s = sum(tot.values())
                shares = {g: v / s for g, v in tot.items()}
            for ms in pd.date_range(pd.Timestamp(r.period_start), pd.Timestamp(r.period_end), freq="MS"):
                ym = f"{ms:%Y%m}"
                gi = self._tp_frame("Grid_import", ym, "POC", r.poc, extra)
                if gi is None or gi.to_numpy().sum() == 0:
                    raise RuntimeError(f"{r.override_id}: no Grid_import at {r.poc} in {ym}")
                ratio, used = (1.0, [("measured", 1.0)]) if measured else self._gm_gi_ratio(r.poc, ym)
                total = gi * ratio
                if extra:
                    # a selected stream carries only this row's generators: subtract only their
                    # own metered output (other generators at the POC sit in other streams)
                    parts = [self._tp_frame("Generation_MD", ym, "POC_Code", r.poc, {"Gen_Code": g}) for g in gens]
                    parts = [p for p in parts if p is not None]
                    metered = sum(parts[1:], parts[0]) if parts else None
                else:
                    metered = self._tp_frame("Generation_MD", ym, "POC_Code", r.poc)
                if metered is not None:
                    metered = metered.reindex(columns=total.columns, fill_value=0.0)
                other = metered.reindex(total.index, fill_value=0.0) if metered is not None else total * 0.0
                if others is not None and len(others):
                    o = others[(others.poc == r.poc) & (others.trading_date.dt.strftime("%Y%m") == ym)]
                    if len(o):
                        o = o.pivot_table(index="trading_date", columns="tp", values="gen_mwh", aggfunc="sum")
                        o.columns = [f"TP{int(c)}" for c in o.columns]
                        other = other.add(o.reindex(index=total.index, columns=total.columns, fill_value=0.0), fill_value=0.0)
                resid = total - other
                resid_total = float(resid.to_numpy().sum())
                shaped = resid.clip(lower=0.0)
                clipped = float(shaped.to_numpy().sum()) - resid_total
                if resid_total <= 0:
                    raise RuntimeError(f"{r.override_id}: non-positive residual in {ym}")
                shaped = shaped * (resid_total / shaped.to_numpy().sum())
                self.grid_import_log.append(dict(override_id=r.override_id, poc=r.poc, month=ym,
                                                 grid_import_mwh=float(gi.to_numpy().sum()), ratio=ratio,
                                                 ratio_months=";".join(f"{m}:{v:.4f}" for m, v in used),
                                                 other_mwh=float(other.to_numpy().sum()), fill_mwh=resid_total,
                                                 clipped_mwh=clipped, shares=shares))
                for day, row in shaped.iterrows():
                    for i, v in enumerate(row.to_numpy(), start=1):
                        if v > 0:
                            for g, sh in shares.items():
                                rows.append((day, i, v * sh, r.override_id, r.fill_basis, r.poc, g, r.parameter.split("_")[-1]))
        return pd.DataFrame(rows, columns=["trading_date", "tp", "gen_mwh", "override_id", "fill_basis",
                                           "poc", "gen_code", "fuel_code_raw"])

    def fills(self):
        """All flagged fills as trading-period rows with poc, gen_code and raw fuel code."""
        m = self.matahina_fill().assign(poc="MAT1101", gen_code="matahina", fuel_code_raw="Hydro")
        h = self.huntly_fill().assign(poc="HLY2201", gen_code="huntly_1_4", fuel_code_raw="Coal")
        base = pd.concat([m, h], ignore_index=True)
        base["trading_date"] = pd.to_datetime(base["trading_date"])
        g = self.grid_import_fill(others=base)
        out = pd.concat([base, g], ignore_index=True)
        out["trading_date"] = pd.to_datetime(out["trading_date"])
        # an empty part (no MATAHINA_ rows) would otherwise leave object dtypes
        out["tp"] = out["tp"].astype(int)
        out["gen_mwh"] = out["gen_mwh"].astype(float)
        return out
