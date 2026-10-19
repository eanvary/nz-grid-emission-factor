"""
Derives an annual grid emission factor (EF) from EECA's TIMES-NZ 3.0 (v3.0.8) published
outputs, and sets it beside this project's metered historical EF and MBIE's EDGS 2024 EF,
nationally and by island.

Source: the TIMES-NZ 3.0 Explorer (https://eeca-nz.shinyapps.io/times-nz-v3/), "Download
unfiltered data" for the Steady and Shift scenarios, saved 2026-09-28 to
reference_data/times_nz_3/{steady,shift}_{ele_gen,ele_use,ems,ele_cap}.csv.
Outputs go to reference_data/times_nz_3/derived/.

EF = electricity-sector emissions / generation, per scenario, year and island. TIMES-NZ
publishes no EF itself, so every variant is a derived quantity:

  reported        emissions exactly as TIMES-NZ books them to "Electricity generation",
                  over total generation.
  +coal_cogen     adds coal cogeneration (Glenbrook Steel, North Island in the data), which
                  TIMES-NZ reports as generation but books its combustion emissions elsewhere:
                  coal PJ x 92.65 kt/PJ, the MfE 2025 factor TIMES-NZ itself uses. This is the
                  total-generation variant.
  total_combustion +coal_cogen with geothermal fugitive emissions removed (numerator only).
                  Matches the EDGS island EF(i) on both emission scope (combustion only)
                  and generation scope (total). Used for Module C.
  grid_only       +coal_cogen with distributed solar removed from the denominator (kept for
                  continuity with the first pass; superseded by grid_supplied).
  grid_supplied   +coal_cogen with all embedded generation removed from the denominator and
                  its emissions from the numerator. Embedded = distributed (rooftop) solar plus
                  the six base-year "generic" plants, which TIMES-NZ docs (baseyear.html, 2.6)
                  describe as "smaller embedded or other plants not available in our plant
                  list". Future-build generic peakers, wind and solar farms are grid plants
                  and stay in. Emissions removed:
                    generic biogas and wood cogeneration: fuel PJ x MfE factor, per plant (exact)
                    generic geothermal cogeneration: its own technology row in ems (exact)
                    generic geothermal generation: ESTIMATE, a generation-weighted share of the
                      "Geothermal" technology's emissions, because ems has no plant column.

EDGS comparison:
  national  MBIE's published EF, output/edgs/edgs_annual_targets.csv.
  island    this project's hourly EDGS disaggregation, generation basis, annual
            generation-weighted mean (the phase1_trajectories.py method), recomputed here from
            the current output/edgs/edgs_hourly_*.parquet because the cached
            analysis_paper/tables/phase1_annual_trajectory_projected.csv predates the
            2026-09-22 rebuild. Needs pyarrow (run with the Anaconda interpreter).

Emissions are CO2-e (MfE factors). The thermal part is fuel PJ x factor, which the script
verifies (check_thermal_consistency).
"""
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "reference_data" / "times_nz_3"
OUT = SRC / "derived"
OUT.mkdir(exist_ok=True)

COAL_KT_PER_PJ = 92.65
MFE_KT_PER_PJ = {"Coal": 92.65, "Natural gas": 54.12, "Diesel": 69.39,
                 "Biogas": 0.06, "Wood": 1.52}
TIMES_TO_EDGS = {"Steady": "Reference", "Shift": "Innovation"}
REGION_CODE = {"North Island": "NI", "South Island": "SI", "National": "National"}

# Base-year calibration plants that stand for embedded generation (docs 2.6), plus rooftop solar.
EMBEDDED_GENERIC = {"Generic biogas cogeneration", "Generic geothermal cogeneration",
                    "Generic geothermal generation", "Generic hydro generation",
                    "Generic wind generation", "Generic wood cogeneration"}


def nfc(s):
    return unicodedata.normalize("NFC", s)


def load(kind):
    d = pd.concat([pd.read_csv(SRC / f"{s}_{kind}.csv", encoding="utf-8-sig")
                   for s in ("steady", "shift")], ignore_index=True)
    if "PlantName" in d:
        d["PlantName"] = d.PlantName.map(nfc)
    return d


gen = load("ele_gen")
use = load("ele_use")
ems = load("ems")
ems = ems[ems.SectorGroup == "Electricity generation"]

gen["embedded"] = (gen.Technology == "Distributed solar") | gen.PlantName.isin(EMBEDDED_GENERIC)


def check_thermal_consistency():
    """Emissions should equal fuel PJ x MfE factor for every thermal technology."""
    fuel = use[use.Fuel.isin(MFE_KT_PER_PJ)].copy()
    fuel["kt_expected"] = fuel.Value * fuel.Fuel.map(MFE_KT_PER_PJ)
    exp = fuel.groupby(["Scenario", "Period", "Technology"]).kt_expected.sum()
    got = ems[ems.TechnologyGroup == "Thermal"].groupby(
        ["Scenario", "Period", "Technology"]).Value.sum()
    j = pd.concat([exp, got.rename("kt_reported")], axis=1).fillna(0)
    j["diff"] = j.kt_reported - j.kt_expected
    return j


keys = ["Scenario", "Period", "Region"]
g_tot = gen.groupby(keys).Value.sum().rename("gen_GWh")
g_dist = gen[gen.Technology == "Distributed solar"].groupby(keys).Value.sum().rename("dist_solar_GWh")
g_emb = gen[gen.embedded].groupby(keys).Value.sum().rename("embedded_GWh")
g_geo = gen[gen.TechnologyGroup == "Geothermal"].groupby(keys).Value.sum().rename("geo_GWh")
e_tot = ems.groupby(keys).Value.sum().rename("ems_kt")
e_geo = ems[ems.TechnologyGroup == "Geothermal"].groupby(keys).Value.sum().rename("geo_kt")
coal_cg = use[(use.Technology == "Coal Cogen") & (use.Fuel == "Coal")]
e_cc = (coal_cg.groupby(keys).Value.sum() * COAL_KT_PER_PJ).rename("coal_cogen_kt")

# Emissions of embedded plants, removed in grid_supplied.
emb_fuel = use[use.PlantName.isin(EMBEDDED_GENERIC) & use.Fuel.isin(MFE_KT_PER_PJ)].copy()
emb_fuel["kt"] = emb_fuel.Value * emb_fuel.Fuel.map(MFE_KT_PER_PJ)
e_emb_thermal = emb_fuel.groupby(keys).kt.sum().rename("emb_thermal_kt")
assert set(gen[gen.Technology == "Geothermal Cogen"].PlantName) == {"Generic geothermal cogeneration"}
e_emb_geocg = ems[ems.Technology == "Geothermal Cogen"].groupby(keys).Value.sum().rename("emb_geo_cogen_kt")
geo_plant = gen[gen.Technology == "Geothermal"]
share = (geo_plant[geo_plant.PlantName == "Generic geothermal generation"].groupby(keys).Value.sum()
         / geo_plant.groupby(keys).Value.sum())
e_geo_tech = ems[ems.Technology == "Geothermal"].groupby(keys).Value.sum()
e_emb_geo_est = (e_geo_tech * share).fillna(0).rename("emb_geo_generic_kt_ESTIMATE")

isl = pd.concat([g_tot, g_dist, g_emb, g_geo, e_tot, e_geo, e_cc, e_emb_thermal, e_emb_geocg,
                 e_emb_geo_est], axis=1).fillna(0).reset_index()
nat = isl.groupby(["Scenario", "Period"]).sum(numeric_only=True).reset_index()
nat["Region"] = "National"
df = pd.concat([isl, nat], ignore_index=True)
df["island"] = df.Region.map(REGION_CODE)
df["emb_kt"] = df.emb_thermal_kt + df.emb_geo_cogen_kt + df.emb_geo_generic_kt_ESTIMATE

# kt / GWh = kg / MWh = g / kWh
df["EF_reported"] = df.ems_kt / df.gen_GWh * 1000
df["EF_plus_coal_cogen"] = (df.ems_kt + df.coal_cogen_kt) / df.gen_GWh * 1000
df["EF_grid_only"] = (df.ems_kt + df.coal_cogen_kt) / (df.gen_GWh - df.dist_solar_GWh) * 1000
df["EF_grid_supplied"] = ((df.ems_kt + df.coal_cogen_kt - df.emb_kt)
                          / (df.gen_GWh - df.embedded_GWh) * 1000)
df["EF_grid_supplied_no_addback"] = (df.ems_kt - df.emb_kt) / (df.gen_GWh - df.embedded_GWh) * 1000
# Combustion scope: geothermal fugitive emissions removed, to match the EDGS projection,
# which sets geothermal CO2 to zero (edgs_pipeline/build_edgs_dispatch.py, "TESTED, NOT
# ADOPTED"). Total-generation denominator, so the matched variant for EDGS island EF(i).
df["EF_total_combustion"] = (df.ems_kt + df.coal_cogen_kt - df.geo_kt) / df.gen_GWh * 1000
df["addback_effect_total"] = df.EF_plus_coal_cogen - df.EF_reported
df["addback_effect_grid_supplied"] = df.EF_grid_supplied - df.EF_grid_supplied_no_addback
df["geo_g_per_kWh"] = df.geo_kt / df.geo_GWh.where(df.geo_GWh > 0) * 1000
df = df.sort_values(["Scenario", "Region", "Period"])
df.to_csv(OUT / "times_nz3_ef_by_year.csv", index=False, float_format="%.4f")

# --- metered history (this project), by island and national
hist_isl = pd.read_csv(ROOT / "output" / "annual_emission_factor_NI_SI.csv")
hist_nat = hist_isl.groupby("year")[["total_CO2_kg", "total_gen_MWh"]].sum().reset_index()
hist_nat["island"] = "National"
hist = pd.concat([hist_isl[["island", "year", "total_CO2_kg", "total_gen_MWh"]], hist_nat])
hist["metered_EF"] = hist.total_CO2_kg / hist.total_gen_MWh  # kg/MWh = g/kWh

# --- comparison 1: national, TIMES-NZ vs MBIE EDGS 2024 published EF vs metered
edgs = pd.read_csv(ROOT / "output" / "edgs" / "edgs_annual_targets.csv")
edgs = edgs[edgs.metric == "grid_emission_factor"][["scenario", "year", "value"]]
edgs["EDGS_EF"] = edgs.value * 1000  # kg/kWh -> g/kWh

n = df[df.Region == "National"].copy()
n["edgs_scenario"] = n.Scenario.map(TIMES_TO_EDGS)
cmp = n.merge(edgs, left_on=["edgs_scenario", "Period"], right_on=["scenario", "year"], how="left")
cmp = cmp.merge(hist[hist.island == "National"][["year", "metered_EF"]].rename(columns={"year": "Period"}),
                on="Period", how="left")
cmp = cmp[["Scenario", "edgs_scenario", "Period", "EF_reported", "EF_plus_coal_cogen",
           "EF_grid_only", "EF_grid_supplied", "EDGS_EF", "metered_EF", "geo_g_per_kWh"]]
cmp.to_csv(OUT / "times_nz3_vs_edgs_vs_metered.csv", index=False, float_format="%.2f")


# --- comparison 2: island, TIMES-NZ vs this project's EDGS island EF(i), generation basis
def edgs_island_annual():
    """Annual generation-weighted EF by scenario x island, generation basis (phase1 method)."""
    E = ROOT / "output" / "edgs"
    ef = pd.read_parquet(E / "edgs_hourly_emission_factor.parquet",
                         columns=["scenario", "island", "datetime_hour", "ef_basis",
                                  "emission_factor_kg_co2e_per_kwh"])
    ef = ef[(ef.ef_basis == "generation") & ef.scenario.isin(TIMES_TO_EDGS.values())].copy()
    g = pd.read_parquet(E / "edgs_hourly_generation.parquet",
                        columns=["scenario", "island", "datetime_hour", "generation_mwh"])
    g = g[g.scenario.isin(TIMES_TO_EDGS.values())]
    gi = g.groupby(["scenario", "island", "datetime_hour"], observed=True).generation_mwh.sum().reset_index()
    gn = gi.groupby(["scenario", "datetime_hour"], observed=True).generation_mwh.sum().reset_index()
    gn["island"] = "National"
    w = pd.concat([gi, gn], ignore_index=True)
    for d in (ef, w):
        d["scenario"] = d.scenario.astype(str)
        d["island"] = d.island.astype(str)
    m = ef.merge(w, on=["scenario", "island", "datetime_hour"], how="left")
    if m.generation_mwh.isna().any():
        raise RuntimeError("EDGS EF rows without a generation weight")
    m["year"] = m.datetime_hour.dt.year
    return (m.groupby(["scenario", "island", "year"])
            .apply(lambda x: np.average(x.emission_factor_kg_co2e_per_kwh, weights=x.generation_mwh) * 1000,
                   include_groups=False)
            .rename("EDGS_island_EF").reset_index())


EDGS_ISL_CACHE = OUT / "edgs_island_annual_generation_basis.csv"
try:
    edgs_isl = edgs_island_annual()
    edgs_isl.to_csv(EDGS_ISL_CACHE, index=False, float_format="%.4f")
except ImportError:
    if not EDGS_ISL_CACHE.exists():
        raise
    edgs_isl = pd.read_csv(EDGS_ISL_CACHE)
    print(f"pyarrow unavailable: using cached {EDGS_ISL_CACHE.name}")

ic = df[["Scenario", "Period", "island", "EF_plus_coal_cogen", "EF_grid_supplied",
         "EF_total_combustion", "addback_effect_total", "addback_effect_grid_supplied"]].copy()
ic["edgs_scenario"] = ic.Scenario.map(TIMES_TO_EDGS)
ic = ic.merge(edgs_isl, left_on=["edgs_scenario", "island", "Period"],
              right_on=["scenario", "island", "year"], how="left").drop(columns=["scenario", "year"])
ic = ic.merge(hist[["island", "year", "metered_EF"]].rename(columns={"year": "Period"}),
              on=["island", "Period"], how="left")
ic["gridsup_minus_EDGS"] = ic.EF_grid_supplied - ic.EDGS_island_EF
ic["total_minus_EDGS"] = ic.EF_plus_coal_cogen - ic.EDGS_island_EF
ic["matched_minus_EDGS"] = ic.EF_total_combustion - ic.EDGS_island_EF
ic = ic.sort_values(["Scenario", "island", "Period"])
ic.to_csv(OUT / "times_nz3_vs_edgs_island.csv", index=False, float_format="%.2f")

# --- 2023 scope reconciliation: TIMES-NZ plants vs metered Generation_MD generators
# TIMES plant(s) -> metered Gen_Code(s). Plants listed together are one station or scheme.
PLANT_MAP = [
    (["Glenbrook Steel"], ["glenbrook_kilns"]),
    (["Huntly Units 1-4"], ["huntly_1_4"]),
    (["Huntly Unit 5 (E3P)"], ["huntly_e3p"]),
    (["Huntly Unit 6 (P40)"], ["huntly_p40"]),
    (["Taranaki Combined Cycle", "Stratford Peaker"], ["stratford"]),
    (["Junction Road"], ["junctionroad"]),
    (["McKee"], ["McKee"]),
    (["Fonterra Dairy - Whareroa"], ["whareroa"]),
    (["Kapuni"], ["kapuni"]),
    (["Te Rapa"], ["te_rapa"]),
    (["Kinleith"], ["kinleith"]),
    (["Kawerau", "TOPP1", "Te Ahi O Maui"], ["kawerau", "kawerau_new", "norskeskog"]),
    (["Mokai"], ["mokai"]),
    (["Nga Awa Pūrua"], ["nap"]),
    (["Ngā Tamariki"], ["Ngatamariki"]),
    (["Ngāwhā (OEC1-3)", "Ngāwhā (OEC4)"], ["ngawha"]),
    (["Poihipi"], ["poihipi"]),
    (["Rotokawa"], ["rotokawa"]),
    (["Te Huka Binary"], ["tehuka"]),
    (["Te Mihi"], ["te_mihi"]),
    (["Wairākei"], ["wairakei"]),
    (["Ōhaaki"], ["ohaaki"]),
    (["Branch River (Argyle + Wairau)"], ["argyle_wairau"]),
    (["Aniwhenua"], ["aniwhenua"]),
    (["Arapuni"], ["arapuni"]),
    (["Aratiatia"], ["aratiatia"]),
    (["Kaimai Hydro Scheme"], ["kaimai"]),
    (["Kaitawa", "Piripaua", "Tuai"], ["waikaremoana"]),
    (["Karāpiro"], ["karapiro"]),
    (["Mangahao"], ["mangahao"]),
    (["Maraetai"], ["maraetai"]),
    (["Matahina"], []),
    (["Patea"], ["patea"]),
    (["Rangipo"], ["rangipo"]),
    (["Tokaanu/Mangaio"], ["tokaanu"]),
    (["Waipāpa"], ["waipapa"]),
    (["Whakamaru"], ["whakamaru"]),
    (["Wheao and Flaxy"], ["wheao_flaxy"]),
    (["Ātiamuri"], ["atiamuri"]),
    (["Ōhakuri"], ["ohakuri"]),
    (["Aviemore"], ["aviemore"]),
    (["Benmore"], ["benmore"]),
    (["Clyde"], ["clyde"]),
    (["Cobb"], ["cobb"]),
    (["Coleridge"], ["coleridge"]),
    (["Highbank"], ["highbank"]),
    (["Manapōuri"], ["manapouri"]),
    (["Paerau Gorge"], ["paerau"]),
    (["Roaring Meg"], []),
    (["Roxburgh"], ["roxburgh"]),
    (["Takapō A"], ["tekapo_a"]),
    (["Takapō B"], ["tekapo_b"]),
    (["Teviot"], ["teviot"]),
    (["Waipori"], ["waipori", "Waipori"]),
    (["Waitaki"], ["waitaki"]),
    (["Ōhau A"], ["ohau_a"]),
    (["Ōhau B"], ["ohau_b"]),
    (["Ōhau C"], ["ohau_c"]),
    (["Mill Creek"], ["mill_creek"]),
    (["Tararua Stage 1 & 2"], ["twf_12"]),
    (["Tararua Stage 3"], ["twf_3"]),
    (["Te Rere Hau"], ["te_rere_hau"]),
    (["Te Uku"], ["te_uku"]),
    (["Te Āpiti"], ["te_apiti"]),
    (["Turitea North", "Turitea South"], ["turitea"]),
    (["Waipipi"], ["waipipi"]),
    (["West Wind"], ["west_wind"]),
    (["Kaiwera Downs Stage 1"], ["KaiweraDowns"]),
    (["White Hill"], ["white_hill"]),
    ([], ["Harapaki", "whirinaki", "southdown", "Tauhara"]),
]
NAMED_COGEN = {"Glenbrook Steel", "Fonterra Dairy - Whareroa", "Kapuni", "Te Rapa", "Kinleith"}


def metered_2023_by_gen_code():
    parts = []
    for f in sorted((ROOT / "EA_EMI_raw").glob("2023??_Generation_MD.csv")):
        d = pd.read_csv(f, low_memory=False)
        tp = [c for c in d.columns if re.match(r"^TP\d+$", c) and int(c[2:]) <= 50]
        d["GWh"] = d[tp].sum(axis=1, skipna=True) / 1e6
        parts.append(d[["Gen_Code", "GWh"]])
    if len(parts) != 12:
        raise RuntimeError(f"expected 12 monthly Generation_MD files for 2023, found {len(parts)}")
    return pd.concat(parts).groupby("Gen_Code").GWh.sum()


def reconcile_2023():
    t = gen[(gen.Scenario == "Steady") & (gen.Period == 2023)]
    t_plant = t.groupby("PlantName").Value.sum()
    m = metered_2023_by_gen_code()
    embedded = t[t.embedded].groupby(["Technology", "PlantName", "Region"]).Value.sum()
    rows = [{"category": "embedded, excluded in grid_supplied",
             "times_plants": f"{tech}: {p} ({r})", "metered_gen_codes": "",
             "times_GWh": v, "metered_GWh": 0.0} for (tech, p, r), v in embedded.items()]
    mapped_t, mapped_m = set(t[t.embedded].PlantName), set()
    for tp, mc in PLANT_MAP:
        mapped_t.update(tp)
        mapped_m.update(mc)
        tv = sum(t_plant.get(p, 0.0) for p in tp)
        mv = sum(m.get(c, 0.0) for c in mc)
        if not tp:
            cat = "metered only (not in TIMES 2023)"
        elif not mc:
            cat = "TIMES only (no Generation_MD record)"
        elif set(tp) & NAMED_COGEN:
            cat = "named cogeneration"
        else:
            cat = "named grid plant"
        rows.append({"category": cat, "times_plants": " + ".join(tp),
                     "metered_gen_codes": " + ".join(mc), "times_GWh": tv, "metered_GWh": mv})
    missing_t = set(t_plant.index) - mapped_t
    missing_m = set(m.index) - mapped_m
    if missing_t or missing_m:
        raise RuntimeError(f"unmapped plants: TIMES {sorted(missing_t)}, metered {sorted(missing_m)}")
    r = pd.DataFrame(rows)
    r["diff_GWh"] = r.times_GWh - r.metered_GWh
    return r


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)
    chk = check_thermal_consistency().reset_index()
    print(f"thermal consistency: max |reported - fuel x MfE| = {chk['diff'].abs().max():.2f} kt "
          f"over {len(chk)} cells; excluding Coal Cogen: "
          f"{chk[chk.Technology != 'Coal Cogen']['diff'].abs().max():.2f} kt")
    rec = reconcile_2023()
    rec.to_csv(OUT / "times_nz3_scope_reconciliation_2023.csv", index=False, float_format="%.1f")
    print("\n2023 reconciliation, TIMES total vs metered (GWh):")
    print(rec.groupby("category")[["times_GWh", "metered_GWh", "diff_GWh"]].sum().round(1).to_string())
    print(f"totals: TIMES {rec.times_GWh.sum():.1f}, metered {rec.metered_GWh.sum():.1f}, "
          f"diff {rec.diff_GWh.sum():.1f}")
    print(cmp.round(1).to_string(index=False))
