"""
journal_palette.py
Reusable color system for Python-generated figures in Q1 journal papers
(building performance / energy simulation work).

Derived from a presentation palette, adapted for print/PDF figure standards:
- White/transparent backgrounds only (no dark panels)
- WCAG-checked contrast against white (see comments)
- Colorblind-aware ordering (deuteranopia/protanopia safe when combined
  with the linestyle/marker redundancy built into set_journal_style)
- Consistent categorical order so the same variable always gets the same
  color across every figure in every paper

Usage:
    from journal_palette import set_journal_style, CATEGORICAL, seq_cmap, div_cmap
    set_journal_style()
    fig, ax = plt.subplots(figsize=(3.5, 2.6))  # single-column width
    for i, series in enumerate(data):
        ax.plot(x, series, color=CATEGORICAL[i], **LINE_STYLES[i])
"""

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from cycler import cycler

# 1. BASE PALETTE (kept from the brand identity, contrast-checked vs white)
# Contrast ratio vs white (WCAG). >=3:1 is the accepted floor for graphical
# objects / thick lines; text and thin lines should stay above ~4.5:1.
BASE = {
    "deep_navy":    "#1A2744",  # contrast 14.8 : 1  -> primary series, titles
    "steel_blue":   "#3A4A5C",  # contrast  9.1 : 1  -> secondary series
    "carbon_teal":  "#0D7377",  # contrast  5.6 : 1  -> accent series
    "teal_light":   "#14919B",  # contrast  3.8 : 1  -> use thicker lines only
    "amber_print":  "#B8720E",  # contrast  3.9 : 1  -> darkened from #E8A838
                                  #  (original amber is 2.1:1 - too low for
                                  #   lines/text, kept below for fills only)
    "amber_fill":   "#E8A838",  # ONLY for filled bars/patches with a dark
                                  # edgecolor, never for thin lines or text
    "muted_slate":  "#8896A7",  # contrast  3.0 : 1  -> gridlines, reference
                                  # lines, non-focal annotation only
    "cloud":        "#E8ECF1",  # contrast  1.2 : 1  -> shaded zones/bands
                                  # only, never for text or line color
}

# 2. CATEGORICAL SEQUENCE
# Ordered by descending contrast/luminance separation so the sequence still
# reads correctly if a reviewer or the printer renders in grayscale, and
# alternates cool/warm hues so it stays distinguishable for red-green
# color-vision deficiency (the navy/teal/amber backbone mirrors the
# Okabe-Ito colorblind-safe logic: blue-family vs orange-family).
CATEGORICAL = [
    BASE["deep_navy"],
    BASE["amber_print"],
    BASE["carbon_teal"],
    BASE["steel_blue"],
    BASE["teal_light"],
    BASE["muted_slate"],
]

# Redundant encoding: pair each color with a distinct linestyle/marker so
# series are still distinguishable if a reader is colorblind or the figure
# is printed in black and white (many building-science journals still do).
LINE_STYLES = [
    {"linestyle": "-",  "marker": "o"},
    {"linestyle": "--", "marker": "s"},
    {"linestyle": "-.", "marker": "^"},
    {"linestyle": ":",  "marker": "D"},
    {"linestyle": "-",  "marker": "v"},
    {"linestyle": "--", "marker": "P"},
]

# 3. CONTINUOUS COLORMAPS (for heatmaps, contour plots, sensitivity grids)
# Sequential: Cloud -> Teal Light -> Carbon Teal -> Deep Navy
# Diverging:  Amber(print) -> White -> Carbon Teal  (warm/cool, e.g. energy
#             increase vs. saving, overheating vs. comfort)
# Both are built from the checked colors above so they stay legible when
# a journal downsamples or greyscales the figure.
def seq_cmap():
    return LinearSegmentedColormap.from_list(
        "journal_sequential",
        [BASE["cloud"], BASE["teal_light"], BASE["carbon_teal"], BASE["deep_navy"]],
        N=256,
    )

def div_cmap():
    return LinearSegmentedColormap.from_list(
        "journal_diverging",
        [BASE["amber_print"], "#FFFFFF", BASE["carbon_teal"]],
        N=256,
    )

# 4. GLOBAL RCPARAMS FOR PUBLICATION FIGURES
# Sizes are tuned for a single-column figure (~3.5 in / 89 mm wide) at the
# FINAL print size: not for on-screen or slide viewing. Scale up figsize
# for double-column (~7 in / 180 mm) figures; keep font sizes as-is so text
# stays proportionate once placed in the journal template.
def set_journal_style():
    plt.rcParams.update({
        # Fonts: sans-serif family that is bundled with matplotlib
        # (DejaVu Sans) so figures render identically on any machine and
        # embed cleanly in PDF/EPS without licensing issues. Swap to
        # "Arial" only if the journal explicitly requires it AND you
        # confirm the font is installed in your build environment.
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "figure.titlesize": 10,

        # Backgrounds: transparent/white only, never navy/dark panels
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.transparent": False,

        # Line & marker weight for print legibility at small size
        "lines.linewidth": 1.2,
        "lines.markersize": 4,
        "axes.linewidth": 0.6,
        "grid.linewidth": 0.4,
        "grid.color": BASE["muted_slate"],
        "grid.alpha": 0.35,

        # Text/axis color: deep navy reads better than pure black on white
        # and keeps the identity consistent with the presentation palette
        "text.color": BASE["deep_navy"],
        "axes.edgecolor": BASE["steel_blue"],
        "axes.labelcolor": BASE["deep_navy"],
        "xtick.color": BASE["steel_blue"],
        "ytick.color": BASE["steel_blue"],

        # Output: vector-first. Use savefig(fname, format="pdf") for
        # submission; if a raster is required, override dpi per-figure.
        "savefig.dpi": 600,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,   # embed fonts as real text, not outlines
        "ps.fonttype": 42,

        "axes.prop_cycle": cycler(color=CATEGORICAL),
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
