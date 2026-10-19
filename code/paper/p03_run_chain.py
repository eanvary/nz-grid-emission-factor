"""
Run the analysis_paper steps Paper 03 cites, one process at a time (the laptop has 16 GB), in a
working copy prepared by p03_build_primary_inputs.py. Resumable: a finished step leaves
<copy_root>/done/<step>.ok and is skipped on the next run.
Usage: python p03_run_chain.py <copy_root> <python_exe>
"""
import ctypes, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve(); PY = sys.argv[2]
S = ROOT / "analysis_paper" / "scripts"
STEPS = [  # (label, script, extra env)
    ("load_profiles", S / "phase3_load_profiles.py", {}),
    ("decomposition", S / "phase3_decomposition.py", {}),
    ("decomposition_tmpl2017", S / "phase3_decomposition.py", {"EDGS_TEMPLATE_YEAR": "2017"}),
    ("decomposition_tmpl2023", S / "phase3_decomposition.py", {"EDGS_TEMPLATE_YEAR": "2023"}),
    ("decomposition_tmpl2024", S / "phase3_decomposition.py", {"EDGS_TEMPLATE_YEAR": "2024"}),
    ("contextualise", S / "phase3_contextualise_v2_finalEUI.py", {}),
    ("template_ranking", S / "phase3_template_ranking_check.py", {}),
    ("table3", S / "build_table3_headline.py", {}),
    ("hist_overlap", S / "phase0_hist_overlap2.py", {}),
    ("variance_decomp", S / "phase1_variance_decomp.py", {}),
    ("distributional", S / "phase1_distributional.py", {}),
    ("within_year", S / "phase1_within_year.py", {}),
    ("trajectories", S / "phase1_trajectories.py", {}),
    ("trajectories_fix", S / "phase1_trajectories_fix.py", {}),
    ("template_shape_selection", S / "phase2_template_shape_selection.py", {}),
    ("template_yardstick", S / "phase2_template_yardstick2025.py", {}),
    ("bdg2", ROOT / "analysis_paper" / "sensitivity_realdata_bdg2" / "scripts" / "03_decomposition_real_shapes.py", {}),
]


class MS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_ulong), ("ml", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ("tp", "ap", "tpf", "apf", "tv", "av", "ae")]


def free_gb():
    m = MS(); m.l = ctypes.sizeof(m); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); return m.ap / 2**30


done = ROOT / "done"; done.mkdir(exist_ok=True)
log = open(ROOT / "chain_log.txt", "a", encoding="utf-8")
for label, script, env in STEPS:
    if (done / f"{label}.ok").exists():
        continue
    while free_gb() < 4:
        time.sleep(20)
    t = time.time()
    p = subprocess.run([PY, str(script)], cwd=str(ROOT), capture_output=True, text=True, env={**os.environ, **env})
    if p.returncode == 0:
        (done / f"{label}.ok").write_text("ok")
        print(time.strftime("%H:%M:%S"), f"OK   {label} ({time.time() - t:.0f}s)", file=log, flush=True)
    else:
        print(time.strftime("%H:%M:%S"), f"FAIL {label}: {p.stderr[-400:]!r}", file=log, flush=True)
print(time.strftime("%H:%M:%S"), "ALL DONE", file=log, flush=True)
