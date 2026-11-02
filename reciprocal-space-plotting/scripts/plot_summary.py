#!/usr/bin/env python3
"""Generate HK, HL and KL slices with shared intensity limits and native metadata.

Mask/coverage and automatic intensity normalization policies are TO BE UPDATED;
see docs/reciprocal-analysis-status.md.
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nexusformat.nexus as nx

from _plot_common import display_cell, draw_section, provisional_norm
from nxs_analysis_tools.reciprocal import reciprocal_slice, resolve_nxdata


def generate_3panel_summary(nxs_path, output_png, h_val=0.0, k_val=0.0, l_val=0.0,
                            unit_cell=None, cmap="viridis", coordinates="auto", vmin=None, vmax=None):
    nx.nxsetmemory(20000)
    root = nx.nxload(nxs_path)
    data = resolve_nxdata(root)
    sections = [reciprocal_slice(data, plane, coord)
                for plane, coord in (("HK", l_val), ("HL", k_val), ("KL", h_val))]
    cell = display_cell(data, unit_cell, coordinates)
    norm = provisional_norm(sections, vmin, vmax)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), dpi=200, layout="constrained")
    try:
        for ax, section in zip(axes, sections):
            mesh = draw_section(ax, section, cell, norm, cmap)
        fig.colorbar(mesh, ax=list(axes), shrink=0.8, label="Intensity (input units)")
        Path(output_png).resolve().parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_png, dpi=300)
    finally:
        plt.close(fig)
    print(f"Saved 3-panel summary plot: {output_png}")


def main():
    parser = argparse.ArgumentParser(description="Generate metadata-resolved HK, HL and KL slices.")
    parser.add_argument("--nxs", required=True, help="3D NeXus reciprocal volume")
    parser.add_argument("--output", "-o", required=True, help="Output PNG path")
    parser.add_argument("--h", type=float, default=0.0, help="H coordinate for KL")
    parser.add_argument("--k", type=float, default=0.0, help="K coordinate for HL")
    parser.add_argument("--l", type=float, default=0.0, help="L coordinate for HK")
    parser.add_argument("--unit-cell", help="Override native sample/unit_cell: a,b,c,alpha,beta,gamma (Å, degrees)")
    parser.add_argument("--coordinates", choices=["auto", "rlu", "physical"], default="auto")
    parser.add_argument("--vmin", type=float)
    parser.add_argument("--vmax", type=float)
    parser.add_argument("--cmap", default="viridis")
    args = parser.parse_args()
    generate_3panel_summary(args.nxs, args.output, args.h, args.k, args.l, args.unit_cell,
                            args.cmap, args.coordinates, args.vmin, args.vmax)


if __name__ == "__main__":
    main()
