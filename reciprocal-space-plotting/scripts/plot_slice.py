#!/usr/bin/env python3
"""Generate a lazy, metadata-resolved reciprocal plane with an optional physical metric.

Mask/coverage and automatic intensity normalization policies are TO BE UPDATED;
see docs/reciprocal-analysis-status.md. Explicit color limits are supported.
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nexusformat.nexus as nx

from _plot_common import display_cell, draw_section, provisional_norm
from nxs_analysis_tools.reciprocal import reciprocal_slice, resolve_nxdata


def plot_single_slice(nxs_path, plane, coord, output_png, unit_cell=None,
                      vmin=None, vmax=None, cmap="viridis", coordinates="auto"):
    nx.nxsetmemory(20000)
    root = nx.nxload(nxs_path)
    data = resolve_nxdata(root)
    section = reciprocal_slice(data, plane=plane, coord=coord)
    cell = display_cell(data, unit_cell, coordinates)
    fig, ax = plt.subplots(figsize=(6, 5), dpi=200)
    try:
        im = draw_section(ax, section, cell, provisional_norm([section], vmin, vmax), cmap)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Intensity (input units)")
        Path(output_png).resolve().parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(output_png, dpi=300)
    finally:
        plt.close(fig)
    print(f"Saved reciprocal slice: {output_png}")


def main():
    parser = argparse.ArgumentParser(description="Generate a metadata-resolved reciprocal space slice.")
    parser.add_argument("--nxs", required=True, help="3D NeXus reciprocal volume")
    parser.add_argument("--plane", default="HK", choices=["HK", "HL", "KL"])
    parser.add_argument("--coord", type=float, default=0.0, help="Perpendicular coordinate in r.l.u.")
    parser.add_argument("--output", "-o", required=True, help="Output PNG path")
    parser.add_argument("--unit-cell", help="Override native sample/unit_cell: a,b,c,alpha,beta,gamma (Å, degrees)")
    parser.add_argument("--coordinates", choices=["auto", "rlu", "physical"], default="auto",
                        help="auto uses the physical metric when a cell is available; otherwise r.l.u.")
    parser.add_argument("--vmin", type=float, help="Explicit positive logarithmic lower limit")
    parser.add_argument("--vmax", type=float, help="Explicit logarithmic upper limit")
    parser.add_argument("--cmap", default="viridis")
    args = parser.parse_args()
    plot_single_slice(args.nxs, args.plane, args.coord, args.output, args.unit_cell,
                      args.vmin, args.vmax, args.cmap, args.coordinates)


if __name__ == "__main__":
    main()
