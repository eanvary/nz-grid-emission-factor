"""Island consumption balance shared by the monthly/annual and daily/hourly consumption scripts."""
import numpy as np
import pandas as pd


def build_consumption(gen_df, hvdc_df, group_keys):
    ni = gen_df[gen_df.island == "NI"].set_index(group_keys)
    si = gen_df[gen_df.island == "SI"].set_index(group_keys)
    h = hvdc_df.set_index(group_keys)

    idx = ni.index.union(si.index).union(h.index)
    ni = ni.reindex(idx, fill_value=0.0)
    si = si.reindex(idx, fill_value=0.0)
    h = h.reindex(idx, fill_value=0.0)

    out = pd.DataFrame(index=idx)
    out["NI_generation_MWh"] = ni["total_gen_MWh"]
    out["NI_CO2_generated_kg"] = ni["total_CO2_kg"]
    out["NI_EF_generation"] = (ni["total_CO2_kg"] / ni["total_gen_MWh"]).replace([np.inf, -np.inf], np.nan)
    out["SI_generation_MWh"] = si["total_gen_MWh"]
    out["SI_CO2_generated_kg"] = si["total_CO2_kg"]
    out["SI_EF_generation"] = (si["total_CO2_kg"] / si["total_gen_MWh"]).replace([np.inf, -np.inf], np.nan)
    out["SI_to_NI_MWh"] = h["SI_to_NI_MWh"]
    out["NI_to_SI_MWh"] = h["NI_to_SI_MWh"]
    out["net_to_NI_MWh"] = h["net_to_NI_MWh"]

    out["NI_consumption_MWh"] = out["NI_generation_MWh"] + out["net_to_NI_MWh"]
    out["SI_consumption_MWh"] = out["SI_generation_MWh"] - out["net_to_NI_MWh"]

    out["NI_CO2_consumed_kg"] = (
        out["NI_CO2_generated_kg"] - out["NI_to_SI_MWh"] * out["NI_EF_generation"]
        + out["SI_to_NI_MWh"] * out["SI_EF_generation"]
    )
    out["SI_CO2_consumed_kg"] = (
        out["SI_CO2_generated_kg"] - out["SI_to_NI_MWh"] * out["SI_EF_generation"]
        + out["NI_to_SI_MWh"] * out["NI_EF_generation"]
    )
    out["NI_EF_consumption"] = out["NI_CO2_consumed_kg"] / out["NI_consumption_MWh"]
    out["SI_EF_consumption"] = out["SI_CO2_consumed_kg"] / out["SI_consumption_MWh"]
    return out.reset_index()
